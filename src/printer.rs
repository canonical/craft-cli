//! Handling for sending messages to a terminal.

use std::{
    fs,
    io::Write as _,
    sync::{
        Arc, LazyLock, Mutex, MutexGuard, OnceLock,
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

/// A simple text message. See [Event::Text] for usage details.
#[derive(Clone, Debug)]
pub struct Text {
    /// The message to emit.
    pub(crate) message: String,

    /// The destination for this message.
    pub(crate) target: Option<Target>,

    /// Whether or not this message should be permanent.
    ///
    /// Setting this to true does not guarantee its permanence; verbosity
    /// levels take precedence. The flag is only used when the permanence
    /// of the message isn't enforced at a given verbosity level.
    pub(crate) permanent: bool,
}

/// A new progress bar. See [Event::NewProgressBar] for usage details.
#[derive(Clone, Debug)]
pub struct NewProgressBar {
    pub(crate) bar: Arc<Mutex<indicatif::ProgressBar>>,
}

/// Types of message for printing.
#[derive(Clone, Debug)]
pub enum Event {
    /// A simple text message.
    ///
    /// Text events will emit to the specified `target`, and will always be
    /// sent to the log file.
    Text(Text),

    /// A streamed message from a [StreamHandle][crate::streams::StreamHandle].
    ///
    /// Behaves identically to [Event::Text], except it will be silently converted
    /// to [Event::PrintProgressBar] if a progress bar is active.
    Stream(Text),

    /// A logging record event.
    ///
    /// Behaves identically to [Event::Text], except it will be silently converted
    /// to [Event::PrintProgressBar] if a progress bar is active.
    Log(Text),

    /// Create a new progress bar.
    ///
    /// Fails if any other progress bars are already running.
    NewProgressBar(NewProgressBar),

    /// Update progress on the progress bar.
    ///
    /// Fails if there is no progress bar to update.
    UpdateProgressBar(u64),

    /// Finish the progress bar.
    ///
    /// Fails if there is no progress bar to finish.
    FinishProgressBar,

    /// Print a message above the progress bar.
    ///
    /// Fails if there is no progress bar.
    PrintProgressBar(String),
}

/// An internal printer object meant to print from a separate thread.
struct InnerPrinter {
    /// A channel upon which messages can be read.
    ///
    /// If this channel is found to be closed, the program is over and this struct
    /// should begin to destruct itself.
    channel: mpsc::Receiver<Event>,

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
    pub fn new(channel: mpsc::Receiver<Event>) -> Self {
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
        let mut maybe_prv_msg: Option<Text> = None;
        let mut progress_bar: Option<Arc<Mutex<indicatif::ProgressBar>>> = None;

        loop {
            // Wait the standard 3 seconds for a message
            match self.await_event(SPIN_TIMEOUT) {
                Ok(event) => {
                    // If we were spinning, stop
                    if let Some(s) = spinner.take()
                        && let Some(mut prv_msg) = maybe_prv_msg.take()
                    {
                        s.finish_and_clear();
                        let dur = indicatif::HumanDuration(s.elapsed());
                        prv_msg.message = format!("{} (took {:#})", prv_msg.message, dur);
                        self.needs_overwrite = false;
                        self.handle_message(&prv_msg)?;
                    }
                    match event {
                        Event::Text(text) | Event::Log(text) | Event::Stream(text) => {
                            // Store the most recently received message in case we need to
                            // begin displaying a spin loader
                            maybe_prv_msg = Some(text.clone());
                            self.handle_message(&text)?;
                        }
                        Event::NewProgressBar(npb) => {
                            _ = progress_bar.insert(npb.bar);
                        }
                        Event::UpdateProgressBar(delta) => match progress_bar {
                            None => unreachable!(),
                            Some(ref bar) => bar
                                .lock()
                                .expect("Unable to communicate with progress bar")
                                .inc(delta),
                        },
                        Event::FinishProgressBar => match progress_bar {
                            None => unreachable!(),
                            Some(ref bar) => bar
                                .lock()
                                .expect("Unable to communicate with progress bar")
                                .finish(),
                        },
                        Event::PrintProgressBar(message) => match progress_bar {
                            None => unreachable!(),
                            Some(ref bar) => bar
                                .lock()
                                .expect("Unable to communicate with progress bar")
                                .println(message),
                        },
                    }
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
                        .with_message(msg.message.clone())
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
    fn await_event(&self, timeout: Duration) -> ::std::result::Result<Event, RecvTimeoutError> {
        self.channel.recv_timeout(timeout)
    }

    /// Routing method for sending a message to the proper printing logic for a given
    /// message type.
    fn handle_message(&mut self, msg: &Text) -> PyResult<()> {
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
    fn print(&mut self, message: &Text) -> PyResult<()> {
        self.handle_overwrite()?;
        self.stdout.write_line(&message.message)?;
        Ok(())
    }

    /// Print a simple message to stderr.
    fn error(&mut self, message: &Text) -> PyResult<()> {
        self.handle_overwrite()?;
        self.stderr.write_line(&message.message)?;
        Ok(())
    }

    #[expect(unused)]
    /// Handle an incremental progress bar.
    fn progress_bar(&mut self, message: &Text) -> PyResult<()> {
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
    channel: OnceLock<mpsc::Sender<Event>>,

    /// A file handle to write to for logging operations.
    log_handle: Option<fs::File>,

    /// A prefix to prepend to every message.
    prefix: Option<String>,

    /// Whether or not a progress bar is currently running.
    in_progress: bool,
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
    pub fn send(&mut self, event: Event) -> PyResult<()> {
        let prepared_event = self.prepare_event(event)?;
        match prepared_event {
            None => Ok(()),
            Some(event) => match self.channel.get() {
                Some(chan) => {
                    chan.send(event).unwrap();
                    Ok(())
                }
                None => panic!("Receiver closed early?"),
            },
        }
    }

    fn prepare_event(&mut self, mut event: Event) -> PyResult<Option<Event>> {
        match event {
            Event::Text(ref mut text) => {
                let should_emit = self.prepare_text(text)?;

                // If a progress bar is running, throw an error to use `println` instead.
                if self.in_progress {
                    return Err(PyRuntimeError::new_err(
                        "Messages cannot be emitted normally when displaying a progress bar. Use `println` instead.",
                    ));
                }

                match should_emit {
                    true => Ok(Some(event)),
                    false => Ok(None),
                }
            }
            Event::NewProgressBar(_) => {
                if self.in_progress {
                    return Err(PyRuntimeError::new_err(
                        "Attempted to replace an existing progress bar.",
                    ));
                }
                self.in_progress = true;
                Ok(Some(event))
            }
            Event::FinishProgressBar => {
                if !self.in_progress {
                    return Err(PyRuntimeError::new_err(
                        "No progress bar available to update.",
                    ));
                }
                self.in_progress = false;
                Ok(Some(event))
            }
            Event::UpdateProgressBar(_) | Event::PrintProgressBar(_) => {
                if !self.in_progress {
                    return Err(PyRuntimeError::new_err(
                        "No progress bar available to update.",
                    ));
                }
                Ok(Some(event))
            }
            Event::Stream(ref mut text) | Event::Log(ref mut text) => {
                let should_emit = self.prepare_text(text)?;

                // Although normally a Text-based event should fail while a progress bar
                // is active, Logs and Streams can't really be held to the same rules as
                // they can happen outside of an Emitter user's control (e.g. an external
                // library creating a log record). Therefore, they should be sent via
                // ProgressBar::println(). However, skip any that wouldn't have been printed
                // anyways to preserve verbosity rules.
                if self.in_progress && should_emit {
                    let new_event = Event::PrintProgressBar(text.message.clone());
                    return Ok(Some(new_event));
                }

                match should_emit {
                    true => Ok(Some(event)),
                    false => Ok(None),
                }
            }
        }
    }

    /// Prepare a text-based event and return if it should be emitted.
    fn prepare_text(&mut self, text: &mut Text) -> PyResult<bool> {
        self.log(&text.message)?;
        // Skip after logging if there's nowhere to even send it
        if text.target.is_none() {
            return Ok(false);
        }
        self.apply_prefix(text);
        Ok(true)
    }

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

    /// Set a prefix for each message.
    pub fn set_prefix(&mut self, prefix: String) {
        self.prefix = Some(prefix);
    }

    /// Clear the current prefix.
    pub fn clear_prefix(&mut self) {
        self.prefix = None;
    }

    /// Apply the current prefix to a message, if any.
    fn apply_prefix(&self, text: &mut Text) {
        if let Some(prefix) = &self.prefix {
            let prefixed = format!("{prefix} :: {}", text.message);
            text.message = prefixed;
        }
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
