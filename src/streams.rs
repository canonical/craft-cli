//! Stream redirection tools.

use std::{
    io::{self, Read},
    os::fd::{AsRawFd as _, RawFd},
    sync::{
        Arc, OnceLock,
        atomic::{AtomicBool, Ordering},
    },
    thread::{self, JoinHandle},
    time::Duration,
};

use pyo3::{
    Bound, PyRefMut, PyResult, exceptions::PyRuntimeError, pyclass, pymethods, types::PyTuple,
};

use crate::{
    emitter::Verbosity,
    printer::{Message, MessageType, Target},
    utils,
};

/// Number of bytes to read at a time from the pipe.
const PIPE_READER_CHUNK_SIZE: usize = 4096;

/// A handle on a writable stream.
///
/// All messages written to this stream will be sent to the log and emitter.
#[pyclass]
pub struct StreamHandle {
    /// A join handle for the thread monitoring the pipe.
    handle: OnceLock<JoinHandle<PyResult<()>>>,

    /// An atomic bool to signal to the pipe-monitoring thread that it is time to
    /// stop when set to true.
    stop_flag: Arc<AtomicBool>,

    /// The verbosity level to log stream events.
    verbosity: Verbosity,

    /// A handle on the write end of the pipe. This is kept for resource management
    /// reasons so that this struct can decide when/where to drop the handle on this
    /// pipe.
    write: Option<io::PipeWriter>,
}

#[pymethods]
impl StreamHandle {
    /// Enter the context manager.
    #[pyo3(name = "__enter__")]
    fn enter(mut slf: PyRefMut<'_, Self>) -> PyResult<PyRefMut<'_, Self>> {
        let (read, write) = io::pipe()?;

        slf.write = Some(write);

        let verbosity = slf.verbosity;
        let stop_flag = Arc::clone(&slf.stop_flag);
        let handle = thread::spawn(move || PipeListener::begin(read, verbosity, stop_flag));

        if slf.handle.set(handle).is_err() {
            return Err(PyRuntimeError::new_err(
                "Internal error: thread handle was already allocated!",
            ));
        }

        Ok(slf)
    }

    /// End the context manager.
    #[pyo3(name = "__exit__", signature = (*_args))]
    fn exit(&mut self, _args: Bound<'_, PyTuple>) -> PyResult<()> {
        let handle = match self.handle.take() {
            None => {
                return Err(PyRuntimeError::new_err(
                    "Cannot exit, stream handle was never entered.",
                ));
            }
            Some(handle) => handle,
        };

        self.stop_flag.store(true, Ordering::Relaxed);

        if let Err(e) = handle.join() {
            return Err(PyRuntimeError::new_err(format!(
                "Stream handler thread panicked: {e:?}"
            )));
        }

        _ = self.write.take();

        // Clear the prefix set when this context manager was entered
        crate::printer::printer().clear_prefix();

        Ok(())
    }

    /// Get a writable file descriptor for this object.
    fn fileno(&self) -> PyResult<RawFd> {
        match &self.write {
            Some(write) => Ok(write.as_raw_fd()),
            None => Err(PyRuntimeError::new_err(
                "Cannot get a fileno of an uninitialized StreamHandle.",
            )),
        }
    }
}

impl StreamHandle {
    /// Construct a new StreamHandle using the verbosity of the rest of the program.
    pub fn new(verbosity: Verbosity) -> Self {
        Self {
            handle: OnceLock::new(),
            stop_flag: Arc::new(AtomicBool::new(false)),
            verbosity,
            write: None,
        }
    }
}

/// An internal structure for monitoring a pipe for reads.
struct PipeListener {
    /// The verbosity level to send messages to the printer with. This
    /// is additionally used to determine whether messages should be ephemeral
    /// or not.
    verbosity: Verbosity,

    /// When set to true, this listener should exit its event loop and clean up so
    /// its thread can be joined.
    stop_flag: Arc<AtomicBool>,

    /// The leftover content from the last message read from the pipe.
    ///
    /// Since there's no guarantee that the pipe is newline-terminated, any content
    /// beyond the last newline is stored here. Then, on the next read,
    remaining_content: Vec<u8>,
}

impl PipeListener {
    fn begin(
        pipe: io::PipeReader,
        verbosity: Verbosity,
        stop_flag: Arc<AtomicBool>,
    ) -> PyResult<()> {
        Self {
            verbosity,
            stop_flag,
            remaining_content: Vec::new(),
        }
        .listen(pipe)
    }

    /// Listening loop for messages on the read end of the pipe.
    fn listen(&mut self, mut pipe: io::PipeReader) -> PyResult<()> {
        let mut buf = [0u8; PIPE_READER_CHUNK_SIZE];

        let mut poll = mio::Poll::new()?;
        let mut events = mio::Events::with_capacity(128);
        let mut listener = mio::unix::SourceFd(&pipe.as_raw_fd());
        poll.registry()
            .register(&mut listener, mio::Token(0), mio::Interest::READABLE)?;

        while !self.stop_flag.load(Ordering::Relaxed) {
            self.handle_pipe(&mut buf, &mut poll, &mut events, &mut pipe)?;
        }

        // Mio requires explicit deregistration and dropping of resources.
        //
        // For more information: https://docs.rs/mio/1.1.1/mio/event/trait.Source.html#dropping-eventsources
        poll.registry().deregister(&mut listener)?;
        drop(pipe);

        // Once the event loop ends, assume the remaining content is complete
        // and append a newline at the end for it.
        if !self.remaining_content.is_empty() {
            self.send_streamed_message(b"\n")?;
        }

        Ok(())
    }

    /// Helper function to handle pipe events.
    fn handle_pipe(
        &mut self,
        buf: &mut [u8; PIPE_READER_CHUNK_SIZE],
        poll: &mut mio::Poll,
        events: &mut mio::Events,
        pipe: &mut io::PipeReader,
    ) -> PyResult<()> {
        poll.poll(events, Some(Duration::from_millis(100)))?;

        if events.is_empty() {
            return Ok(());
        }

        let num_read = match pipe.read(buf) {
            // No need to exit, we can just try again.
            Err(e) => {
                eprintln!("Failed to read from pipe: {e}");
                return Ok(());
            }
            Ok(num_read) => {
                // Don't send a message if we didn't receive anything.
                if num_read == 0 {
                    return Ok(());
                }
                num_read
            }
        };

        self.send_streamed_message(&buf[0..num_read])
    }

    /// Helper function for handling the content read from the pipe.
    fn send_streamed_message(&mut self, message: &[u8]) -> PyResult<()> {
        // Append the new content to the content left over from the previous print
        self.remaining_content.extend_from_slice(message);

        let all_parts = self
            .remaining_content
            .split(|c| *c == b'\n')
            .collect::<Vec<&[u8]>>();

        let (last, parts) = all_parts
            .split_last()
            .expect("Internal error: Attempted to send empty content through stream handle");

        let permanent = self.verbosity >= Verbosity::Verbose;
        let target = match self.verbosity {
            Verbosity::Quiet => None,
            _ => Some(Target::Stderr),
        };

        for part in parts {
            let parsed = String::from_utf8_lossy(part);

            let text = match self.verbosity {
                Verbosity::Debug | Verbosity::Trace => utils::apply_timestamp(&parsed),
                _ => parsed,
            }
            .to_string();

            let message = Message {
                text,
                model: MessageType::Text,
                target,
                permanent,
            };

            crate::printer::printer().send(message)?;
        }

        self.remaining_content = last.to_vec();

        Ok(())
    }
}
