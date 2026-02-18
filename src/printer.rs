//! Handling for sending messages to a terminal.

use std::{
    fs,
    io::Write as _,
    sync::{
        LazyLock, Mutex, MutexGuard, OnceLock,
        mpsc::{self, RecvTimeoutError},
    },
    thread::{self, JoinHandle},
    time::Duration,
};

use pyo3::{PyErr, PyResult, exceptions::PyRuntimeError};

use crate::utils;

/// Duration to wait before beginning to spin.
const SPIN_TIMEOUT: Duration = Duration::from_secs(3);

/// The only printer to ever exist!
///
/// The printer is declared this way in order to allow it being
/// accessed by potentially multiple threads.
///
/// Since PyO3 plays poorly with lifetimes, it isn't possible to
/// pass around a reference to a singular `Printer`. Furthermore,
/// having a `JoinHandle<_>` attached to the `Printer` makes it
/// infeasible to clone or copy the printer between structs, even
/// in an `Arc`.
static PRINTER: LazyLock<Mutex<Printer>> = LazyLock::new(|| Mutex::new(Printer::new()));

/// Get the printer singleton.
///
/// If this is the first get, it will initialize a printer.
pub fn printer<'a>() -> MutexGuard<'a, Printer> {
    PRINTER.lock().unwrap()
}

/// Representation of which stream should be targeted by a message.
#[derive(Debug, Clone, Copy)]
pub enum Target {
    /// Target the stdout stream.
    Stdout,

    /// Target the stderr stream.
    Stderr,
}

impl From<Target> for indicatif::ProgressDrawTarget {
    fn from(val: Target) -> Self {
        match val {
            Target::Stdout => indicatif::ProgressDrawTarget::stdout(),
            Target::Stderr => indicatif::ProgressDrawTarget::stderr(),
        }
    }
}

/// Types of message for printing.
#[derive(Clone, Copy, Debug)]
pub enum MessageType {
    /// Just plain text to display.
    Text,

    // Pending implementation of incremental progress bars using indicatif
    #[expect(unused)]
    /// Signals to create a progress bar.
    ProgBar(u64),
}

/// A single message to be sent, and what type of message it is.
#[derive(Clone, Debug)]
pub struct Message {
    /// The message to be printed.
    pub(crate) text: String,

    // Pending implementation of incremental progress bars using indicatif
    #[expect(unused)]
    /// The type of message to send.
    pub(crate) model: MessageType,

    /// Where the message should be sent.
    pub(crate) target: Option<Target>,

    /// Whether or not this message should persist after the next message.
    ///
    /// Depending on the exact type of message that follows, a non-permanent
    /// message may still remain. Namely, after an error.
    pub(crate) permanent: bool,
}

/// An internal printer object meant to print from a separate thread.
struct InnerPrinter {
    /// A channel upon which messages can be read.
    ///
    /// If this channel is found to be closed, the program is over and this struct
    /// should begin to destruct itself.
    channel: mpsc::Receiver<Message>,

    /// A handle on stdout.
    stdout: console::Term,

    /// A handle on stderr.
    stderr: console::Term,

    /// A flag indicating if the previous line should be overwritten when printing
    /// the next.
    needs_overwrite: bool,
}

impl InnerPrinter {
    /// Instantiate a new `InnerPrinter`.
    pub fn new(channel: mpsc::Receiver<Message>) -> Self {
        let result = Self {
            stdout: console::Term::stdout(),
            stderr: console::Term::stderr(),
            channel,
            needs_overwrite: false,
        };

        // Hide the terminal cursor while taking control
        result.stdout.hide_cursor().unwrap();

        result
    }

    /// Begin listening for messages on `self.channel`.
    ///
    /// This method will block execution until the the corresponding `Sender` for
    /// `self.channel` is closed. As such, it is strongly recommended to only invoke
    /// this from a dedicated thread.
    pub fn listen(&mut self) -> PyResult<()> {
        let main_style =
            indicatif::ProgressStyle::with_template("{spinner} {msg} ({elapsed})").unwrap();
        let mut spinner: Option<indicatif::ProgressBar> = None;
        let mut maybe_prv_msg: Option<Message> = None;

        loop {
            // Wait the standard 3 seconds for a message
            match self.await_message(SPIN_TIMEOUT) {
                Ok(msg) => {
                    // If we were spinning, stop
                    if let Some(s) = spinner.take()
                        && let Some(mut prv_msg) = maybe_prv_msg.take()
                    {
                        s.finish_and_clear();
                        let dur = indicatif::HumanDuration(s.elapsed());
                        prv_msg.text = format!("{} (took {:#})", prv_msg.text, dur);
                        self.needs_overwrite = false;
                        self.handle_message(&prv_msg)?;
                    }
                    // Store the most recently received message in case we need to
                    // begin displaying a spin loader
                    maybe_prv_msg = Some(msg.clone());
                    self.handle_message(&msg)?;
                }
                // Break out of this loop if the channel is closed
                Err(RecvTimeoutError::Disconnected) => break,
                // If the three seconds elapsed, spin
                Err(RecvTimeoutError::Timeout) => {
                    // If we're already spinning on a message, keep waiting
                    if spinner.is_some() {
                        continue;
                    }

                    let msg = match &maybe_prv_msg {
                        Some(msg) => msg,
                        None => continue,
                    };

                    let target = match msg.target {
                        Some(target) => target.into(),
                        None => continue,
                    };

                    let new_spinner = indicatif::ProgressBar::with_draw_target(None, target)
                        .with_style(main_style.clone())
                        .with_message(msg.text.clone())
                        .with_elapsed(SPIN_TIMEOUT);
                    self.stdout.clear_last_lines(1).unwrap();
                    new_spinner.enable_steady_tick(Duration::from_millis(100));
                    spinner = Some(new_spinner);
                }
            }
        }

        Ok(())
    }

    /// Helper method for receiving a message from `self.channel`
    fn await_message(&self, timeout: Duration) -> ::std::result::Result<Message, RecvTimeoutError> {
        self.channel.recv_timeout(timeout)
    }

    /// Routing method for sending a message to the proper printing logic for a given
    /// message type.
    fn handle_message(&mut self, msg: &Message) -> PyResult<()> {
        let res = match msg.target {
            None => return Ok(()),
            Some(target) => match target {
                Target::Stdout => self.print(msg),
                Target::Stderr => self.error(msg),
            },
        };
        self.needs_overwrite = !msg.permanent;
        res
    }

    /// Handle the need (or lackthereof) to overwrite the previous line.
    fn handle_overwrite(&mut self) -> PyResult<()> {
        if self.needs_overwrite {
            self.stdout.clear_last_lines(1)?;
        }
        Ok(())
    }

    /// Print a simple message to stdout.
    fn print(&mut self, message: &Message) -> PyResult<()> {
        self.handle_overwrite()?;
        self.stdout.write_line(&message.text)?;
        Ok(())
    }

    /// Print a simple message to stderr.
    fn error(&mut self, message: &Message) -> PyResult<()> {
        self.handle_overwrite()?;
        self.stderr.write_line(&message.text)?;
        Ok(())
    }

    #[expect(unused)]
    /// Handle an incremental progress bar.
    fn progress_bar(&mut self, message: &Message) -> PyResult<()> {
        unimplemented!()
    }
}

impl Drop for InnerPrinter {
    /// Restore the cursor when releasing control of the terminal.
    fn drop(&mut self) {
        // Attempt to restore sanity, but don't break more if already panicking
        let res = self
            .handle_overwrite()
            .map_or_else(|_| self.stdout.show_cursor(), Ok);
        if let Err(e) = res
            && !thread::panicking()
        {
            eprintln!("Unable to destruct inner printer: {e}");
        }
    }
}

/// Outer handler for printing. Stores a handle to the thread that `InnerPrinter`
/// is printing from, and a channel to send messages.
///
/// Since an mpsc channel is being used, this struct can be arbitrarily cloned,
/// but should always use an existing `InnerPrinter` rather than constructing its
/// own new one.
#[derive(Default)]
pub struct Printer {
    /// A handle on the thread running the `InnerPrinter` instance.
    handle: OnceLock<JoinHandle<PyResult<()>>>,

    /// A channel to send messages to the `InnerPrinter` instance.
    channel: OnceLock<mpsc::Sender<Message>>,

    /// A file handle to write to for logging operations.
    log_handle: Option<fs::File>,
}

impl Printer {
    /// Create a new Printer.
    fn new() -> Self {
        let mut printer = Self::default();
        printer.start();
        printer
    }

    /// Spawn a thread to begin listening for messages to print.
    fn start(&mut self) {
        let (send, recv) = mpsc::channel();

        if self.channel.set(send).is_err() {
            // The printer has already been started.
            return;
        }

        let handle = thread::spawn(move || -> PyResult<()> {
            let mut printer = InnerPrinter::new(recv);
            printer.listen()?;
            Ok(())
        });

        // If this fails, some sort of strange partial initialization state
        // has happened where the send channel was set, but the corresponding
        // thread handle that held the recv end of the channel was not saved.
        //
        // Since `OnceLocks` are only writable once, this is an irrecoverable
        // state. We cannot create a new recv channel to match the already
        // written thread handle.
        self.handle.set(handle).unwrap();
    }

    /// Stop printing.
    ///
    /// This ends the `InnerPrinter` instance's thread.
    pub fn stop(&mut self) -> PyResult<()> {
        // Dropping the channel closes it, which will be seen by the other thread as a
        // stopping condition
        _ = self.channel.take();
        if let Some(handle) = self.handle.take()
            && let Err(e) = handle.join()
        {
            // PyErr should be the only type returned by members of this
            // crate, so we should be safe to blindly downcast. Failures
            // here should be considered bugs rather than unhandled errors
            return Err(*e.downcast::<PyErr>().unwrap());
        }

        Ok(())
    }

    /// Send a message to the `InnerPrinter` for displaying
    pub fn send(&mut self, msg: Message) -> PyResult<()> {
        self.log(&msg.text)?;
        // Skip after logging if there's nowhere to even send it
        if msg.target.is_none() {
            return Ok(());
        }
        match self.channel.get() {
            Some(chan) => chan.send(msg).unwrap(),
            None => panic!("Receiver closed early?"),
        }
        Ok(())
    }
}

impl Printer {
    /// Initialize the logger, if wanted.
    ///
    /// All messages received by the printer will be sent to this log file.
    pub fn init_logger(&mut self, filepath: &str, greeting: &str) -> PyResult<()> {
        if self.log_handle.is_some() {
            return Err(PyRuntimeError::new_err(
                "Logging was already initialized internally.",
            ));
        }

        let log_handle = fs::OpenOptions::new()
            .write(true)
            .truncate(true)
            .create(true)
            .open(filepath)?;

        self.log_handle = Some(log_handle);
        self.log(greeting)?;

        Ok(())
    }

    /// Print a string to the log with a timestamp.
    fn log(&mut self, text: &str) -> PyResult<()> {
        if let Some(log) = self.log_handle.as_mut() {
            let timestamped = utils::apply_timestamp(text);
            writeln!(log, "{timestamped}")?;
        }
        Ok(())
    }
}

impl Drop for Printer {
    fn drop(&mut self) {
        if let Err(e) = self.stop()
            && !thread::panicking()
        {
            if !thread::panicking() {
                eprintln!("Error encountered in printing thread: {e:?}");
            }

            // Make a last-ditch attempt to restore the text cursor before bailing.
            //
            // This should be a no-op if it already succeeded during
            // the tear down of another object, so this really is just insurance
            // to try to leave the shell in a usable state.
            if let Err(e) = console::Term::stdout().show_cursor() {
                eprintln!("Unable to restore text cursor: {e}")
            }
        }
    }
}
