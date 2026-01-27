//! The Emitter class and its associated helpers.

use std::{
    borrow::Cow,
    fs::{self, File},
    io::Write as _,
    path::PathBuf,
    thread,
};

use pyo3::{Bound, PyResult, Python, pyclass, pymethods, pymodule, types::PyType};

use crate::printer::{Message, MessageType, Printer, Target};

/// Verbosity modes.
#[derive(Clone, Copy)]
#[pyclass]
pub enum Verbosity {
    /// Quiet output. Most messages should not be output at all.
    #[pyo3(name = "QUIET")]
    Quiet,

    /// Brief output. Most messages should be ephemeral and all debugging-style message
    /// models should be skipped.
    #[pyo3(name = "BRIEF")]
    Brief,

    /// Verbose mode. All messages should be persistent and all debugging-style messages
    /// kept.
    #[pyo3(name = "VERBOSE")]
    Verbose,

    /// Debug mode. Similar to trace mode, but slightly less information from external
    /// loggers is kept.
    #[pyo3(name = "DEBUG")]
    Debug,

    /// Trace mode. The absolute maximum amount of information should be printed.
    #[pyo3(name = "TRACE")]
    Trace,
}

/// Emitter
#[pyclass]
struct Emitter {
    /// Internal printer instance for sending messages.
    ///
    /// Executes I/O operations in a separate thread to make all logging non-blocking.
    printer: Printer,

    /// A handle to the desired log file.
    log_handle: File,

    /// The original filepath of the log file.
    log_filepath: String,

    // Used by `report_error` on the Python side, which was left in Python due to
    // the retrieved errors all still being in Python.
    #[expect(unused)]
    /// The base URL for error messages.
    docs_base_url: String,

    /// The verbosity mode.
    verbosity: Verbosity,

    /// The greeting the emitter was started with.
    greeting: String,
}

#[pymethods]
impl Emitter {
    /// Construct a new `Emitter` from Python.
    #[new]
    fn new(
        py: Python<'_>,
        log_filepath: String,
        verbosity: Verbosity,
        docs_base_url: &str,
        greeting: String,
    ) -> PyResult<Self> {
        let mut printer = Printer::default();

        // Spawn the printer thread without using the GIL at all
        // This is necessary to avoid deadlocks when using OnceCell, see the link below
        // for more information.
        // https://pyo3.rs/v0.25.1/faq.html#im-experiencing-deadlocks-using-pyo3-with-stdsynconcelock-stdsynclazylock-lazy_static-and-once_cell
        py.detach(|| printer.start(verbosity));

        let log_handle = fs::OpenOptions::new()
            .write(true)
            .truncate(true)
            .create(true)
            .open(&log_filepath)?;

        Ok(Self {
            printer,
            log_handle,
            log_filepath,
            docs_base_url: docs_base_url.trim_end_matches('/').to_string(),
            verbosity,
            greeting,
        })
    }

    /// Create a log filepath from the app name as an easy default.
    #[classmethod]
    fn log_filepath_from_name(_cls: &Bound<'_, PyType>, app_name: &str) -> String {
        let base_dir = dirs::state_dir()
            .unwrap_or(
                std::env::current_dir()
                    .expect("Could not find a suitable log location. As a fallback, make sure the current directory exists.")
            );

        let now = jiff::Timestamp::now();
        let mut log_filepath = PathBuf::new();

        log_filepath.extend([
            app_name,
            "log",
            &now.strftime("%Y%m%d-%H%M%S.%f").to_string(),
        ]);

        let final_path = base_dir.join(log_filepath).with_added_extension("log");
        final_path.display().to_string()
    }

    /// Get the current verbosity mode of the emitter.
    fn get_verbosity(&self) -> Verbosity {
        self.verbosity
    }

    /// Set the verbosity of the emitter.
    fn set_verbosity(&mut self, new: Verbosity) {
        self.verbosity = new;

        if let Verbosity::Verbose | Verbosity::Debug | Verbosity::Trace = new {
            let messages = [
                self.greeting.clone(),
                format!("Logging execution to {}", self.log_filepath),
            ];
            for message in messages {
                self.printer.send(Message {
                    text: message,
                    model: MessageType::Info,
                    target: Some(Target::Stderr),
                });
            }
        }
    }

    /// Verbose information.
    ///
    /// Useful for providing more information to the user that isn't particularly
    /// helpful for "regular use"
    fn verbose(&mut self, text: &str) -> PyResult<()> {
        let timestamped = Self::apply_timestamp(text);
        self.log(&timestamped)?;

        let (maybe_timestamped, target) = match self.verbosity {
            Verbosity::Brief | Verbosity::Quiet => (text, None),
            Verbosity::Verbose => (text, Some(Target::Stderr)),
            Verbosity::Debug | Verbosity::Trace => (timestamped.as_ref(), Some(Target::Stderr)),
        };
        let text = maybe_timestamped.to_string();
        let model = MessageType::Debug;

        let message = Message {
            text,
            model,
            target,
        };

        self.printer.send(message);
        Ok(())
    }

    /// Debug information.
    ///
    /// Use to record anything that the user may not want to normally see, but
    /// would be useful for the app developers to understand why things may be
    /// failing.
    fn debug(&mut self, text: &str) -> PyResult<()> {
        let timestamped = Self::apply_timestamp(text);
        self.log(&timestamped)?;

        let target = match self.verbosity {
            Verbosity::Brief | Verbosity::Quiet | Verbosity::Verbose => None,
            _ => Some(Target::Stderr),
        };
        let text = timestamped.to_string();
        let model = MessageType::Debug;

        let message = Message {
            text,
            model,
            target,
        };

        self.printer.send(message);
        Ok(())
    }

    /// Trace information.
    ///
    /// Use to expose system-generated information which in general would be
    /// overwhelming for debugging purposes but sometimes needed for more
    /// in-depth analysis.
    fn trace(&mut self, text: &str) -> PyResult<()> {
        let timestamped = Self::apply_timestamp(text);
        self.log(&timestamped)?;

        let target = match self.verbosity {
            Verbosity::Trace => Some(Target::Stderr),
            _ => None,
        };
        let text = timestamped.to_string();
        let model = MessageType::Trace;

        let message = Message {
            text,
            model,
            target,
        };

        self.printer.send(message);
        Ok(())
    }

    /// Progress information.
    ///
    /// This is normally used to present several related messages relaying how
    /// a task is going. If a progress message is important enough that it
    /// shouldn't be overwritten by the next ones, use "permanent=True".
    ///
    /// These messages will be truncated to the terminal's width and overwritten
    /// by the next line (unless in verbose or trace mode, or set to permanent).
    #[pyo3(signature = (text, *, permanent = false))]
    fn progress(&mut self, text: &str, mut permanent: bool) -> PyResult<()> {
        let timestamped = Self::apply_timestamp(text);
        self.log(&timestamped)?;

        let (maybe_timestamped, target) = match self.verbosity {
            Verbosity::Quiet => {
                permanent = false;
                (text, None)
            }
            Verbosity::Brief => (text, Some(Target::Stderr)),
            Verbosity::Verbose => {
                permanent = true;
                (text, Some(Target::Stderr))
            }
            _ => {
                permanent = true;
                (timestamped.as_ref(), Some(Target::Stderr))
            }
        };
        let model = if permanent {
            MessageType::ProgPersistent(target)
        } else {
            MessageType::ProgEphemeral(target)
        };
        let text = maybe_timestamped.to_owned();
        let message = Message {
            text,
            model,
            target,
        };

        self.printer.send(message);
        Ok(())
    }

    /// Show a simple message to the user.
    ///
    /// Ideally used as the final message in a sequence to show a result, as it
    /// goes to stdout unlike other message types.
    fn message(&mut self, text: String) -> PyResult<()> {
        let timestamped = Self::apply_timestamp(&text);
        self.log(&timestamped)?;

        let target = match self.verbosity {
            Verbosity::Quiet => None,
            _ => Some(Target::Stdout),
        };
        let model = MessageType::Info;

        let message = Message {
            text,
            model,
            target,
        };

        self.printer.send(message);
        Ok(())
    }

    /// Show an important warning to the user.
    #[pyo3(signature = (text, prefix = "Warning: "))]
    fn warning(&mut self, text: &str, prefix: &str) -> PyResult<()> {
        let prefixed = format!("{}{}", prefix, text);
        let timestamped = Self::apply_timestamp(&prefixed);
        self.log(&timestamped)?;

        let (maybe_timestamped, target) = match self.verbosity {
            Verbosity::Quiet => (prefixed.as_str(), None),
            Verbosity::Debug | Verbosity::Trace => (timestamped.as_ref(), Some(Target::Stderr)),
            _ => (prefixed.as_str(), Some(Target::Stderr)),
        };
        let text = maybe_timestamped.to_string();
        let model = MessageType::Warning;

        let message = Message {
            text,
            model,
            target,
        };

        self.printer.send(message);
        Ok(())
    }

    #[expect(unused)]
    /// Render an incremental progress bar.
    fn progress_bar(&mut self, text: &str, total: u64) -> PyResult<()> {
        unimplemented!()
    }

    /// Stop gracefully.
    fn ended_ok(&mut self) -> PyResult<()> {
        self.finish()
    }
}

impl Emitter {
    /// Apply the timestamp to a message if necessary.
    fn apply_timestamp(text: &str) -> Cow<'_, str> {
        format!(
            "{} {}",
            jiff::Timestamp::now().strftime("%Y-%m-%d %H:%M:%s%.3f"),
            text
        )
        .into()
    }

    /// Print a string to the log.
    fn log(&mut self, text: &str) -> PyResult<()> {
        writeln!(self.log_handle, "{text}")?;
        Ok(())
    }

    /// Stop the printing infrastructure and print a final message to see the logs.
    fn finish(&mut self) -> PyResult<()> {
        let message = Message {
            text: format!("Full execution log at '{}'", self.log_filepath),
            model: MessageType::Info,
            target: Some(Target::Stderr),
        };
        self.printer.send(message);
        self.printer.stop()?;
        Ok(())
    }
}

impl Drop for Emitter {
    fn drop(&mut self) {
        if let Err(e) = self.printer.stop()
            && thread::panicking()
        {
            eprintln!(
                "Unwinding due to panic! The Printer was not stopped correctly. Please report this as a bug: {e}"
            );
        }
    }
}

#[pymodule(submodule)]
pub mod emitter {
    use crate::utils::fix_imports;
    use pyo3::types::PyModule;
    use pyo3::{Bound, PyResult};

    #[pymodule_export]
    use crate::emitter::{Emitter, Verbosity};

    /// Fix syspath for easier importing in Python.
    #[pymodule_init]
    fn init(m: &Bound<'_, PyModule>) -> PyResult<()> {
        fix_imports(m, "craft_cli._rs.emitter")
    }
}
