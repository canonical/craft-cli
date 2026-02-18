//! The Emitter class and its associated helpers.

use std::{path::PathBuf, thread};

use pyo3::{
    Bound, Py, PyAny, PyResult, Python, pyclass, pymethods, pymodule,
    types::{PyAnyMethods as _, PyType},
};

use crate::{
    logs::LogListener,
    printer::{Message, MessageType, Target},
    streams::StreamHandle,
    utils,
};

/// Verbosity modes.
#[derive(Clone, Copy, PartialEq, PartialOrd)]
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

    /// A handle on log handling.
    _log_handle: Option<Py<PyAny>>,

    /// A prefix to prepend to each message.
    prefix: Option<String>,

    /// Whether or not to streamline messages in with "brief" level verbosity.
    ///
    /// With this setting, sending an ephemeral progress message causes
    /// each subsequent ephemeral message to become prefixed with the initial message.
    streaming_brief: bool,
}

#[pymethods]
impl Emitter {
    /// Construct a new `Emitter` from Python.
    ///
    /// This also enables the logging features
    #[new]
    #[pyo3(signature = (log_filepath, verbosity, docs_base_url, greeting, streaming_brief = false))]
    fn new(
        py: Python<'_>,
        log_filepath: String,
        verbosity: Verbosity,
        docs_base_url: &str,
        greeting: String,
        streaming_brief: bool,
    ) -> PyResult<Self> {
        crate::printer::printer().init_logger(&log_filepath, &greeting)?;

        let _log_handle = Self::setup_external_log_capture(py, verbosity, streaming_brief)?;
        Ok(Self {
            log_filepath,
            docs_base_url: docs_base_url.trim_end_matches('/').to_string(),
            verbosity,
            greeting,
            _log_handle,
            prefix: None,
            streaming_brief,
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
    fn set_verbosity(&mut self, new: Verbosity) -> PyResult<()> {
        self.verbosity = new;

        if new >= Verbosity::Verbose {
            let messages = [
                self.greeting.clone(),
                format!("Logging execution to {}", self.log_filepath),
            ];
            for message in messages {
                crate::printer::printer().send(Message {
                    text: message,
                    model: MessageType::Text,
                    target: Some(Target::Stderr),
                    permanent: true,
                })?;
            }
        }

        Ok(())
    }

    /// Verbose information.
    ///
    /// Useful for providing more information to the user that isn't particularly
    /// helpful for "regular use"
    fn verbose(&mut self, text: &str) -> PyResult<()> {
        let timestamped = utils::apply_timestamp(text);

        let (maybe_timestamped, target) = match self.verbosity {
            Verbosity::Brief | Verbosity::Quiet => (text, None),
            Verbosity::Verbose => (text, Some(Target::Stderr)),
            Verbosity::Debug | Verbosity::Trace => (timestamped.as_ref(), Some(Target::Stderr)),
        };
        let text = maybe_timestamped.to_string();

        let mut message = Message {
            text,
            model: MessageType::Text,
            target,
            permanent: true,
        };

        self.apply_prefix(&mut message);
        crate::printer::printer().send(message)?;
        Ok(())
    }

    /// Debug information.
    ///
    /// Use to record anything that the user may not want to normally see, but
    /// would be useful for the app developers to understand why things may be
    /// failing.
    fn debug(&mut self, text: &str) -> PyResult<()> {
        let timestamped = utils::apply_timestamp(text);

        let target = match self.verbosity {
            Verbosity::Brief | Verbosity::Quiet | Verbosity::Verbose => None,
            _ => Some(Target::Stderr),
        };
        let text = timestamped.to_string();

        let mut message = Message {
            text,
            model: MessageType::Text,
            target,
            permanent: true,
        };

        self.apply_prefix(&mut message);
        crate::printer::printer().send(message)?;
        Ok(())
    }

    /// Trace information.
    ///
    /// Use to expose system-generated information which in general would be
    /// overwhelming for debugging purposes but sometimes needed for more
    /// in-depth analysis.
    fn trace(&mut self, text: &str) -> PyResult<()> {
        let timestamped = utils::apply_timestamp(text);

        let target = match self.verbosity {
            Verbosity::Trace => Some(Target::Stderr),
            _ => None,
        };
        let text = timestamped.to_string();

        let mut message = Message {
            text,
            model: MessageType::Text,
            target,
            permanent: true,
        };

        self.apply_prefix(&mut message);
        crate::printer::printer().send(message)?;
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
        let timestamped = utils::apply_timestamp(text);

        // Clear the existing prefix, as we're beginning progress on a new thing now.
        if self.streaming_brief {
            self.clear_prefix();
        }

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

        let final_text = maybe_timestamped.to_owned();

        let message = Message {
            text: final_text,
            model: MessageType::Text,
            target,
            permanent,
        };

        crate::printer::printer().send(message)?;

        // If we're in streaming brief mode and the last message was ephemeral, set this message as the new prefix
        if matches!(self.verbosity, Verbosity::Brief) && !permanent && self.streaming_brief {
            self.set_prefix(text.to_string());
        }

        Ok(())
    }

    /// Show a simple message to the user.
    ///
    /// Ideally used as the final message in a sequence to show a result, as it
    /// goes to stdout unlike other message types.
    fn message(&mut self, text: String) -> PyResult<()> {
        let target = match self.verbosity {
            Verbosity::Quiet => None,
            _ => Some(Target::Stdout),
        };

        let message = Message {
            text,
            model: MessageType::Text,
            target,
            permanent: true,
        };

        crate::printer::printer().send(message)?;
        Ok(())
    }

    /// Show an important warning to the user.
    #[pyo3(signature = (text, prefix = "Warning: "))]
    fn warning(&mut self, text: &str, prefix: &str) -> PyResult<()> {
        let prefixed = format!("{}{}", prefix, text);
        let timestamped = utils::apply_timestamp(&prefixed);

        let (maybe_timestamped, target) = match self.verbosity {
            Verbosity::Quiet => (prefixed.as_str(), None),
            Verbosity::Debug | Verbosity::Trace => (timestamped.as_ref(), Some(Target::Stderr)),
            _ => (prefixed.as_str(), Some(Target::Stderr)),
        };
        let text = maybe_timestamped.to_string();

        let mut message = Message {
            text,
            model: MessageType::Text,
            target,
            permanent: true,
        };

        self.apply_prefix(&mut message);
        crate::printer::printer().send(message)?;
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

    /// Open a stream context manager to redirect output to a different stream.
    #[cfg(unix)]
    fn open_stream(&self) -> StreamHandle {
        StreamHandle::new(self.verbosity)
    }

    /// Open a stream context manager to redirect output to a different stream.
    #[cfg(windows)]
    fn open_stream(&self) -> PyResult<()> {
        use pyo3::exceptions::PyNotImplementedError;

        // The Python implementation of this hinged upon the fact that Python accepts
        // C-style integer file descriptors on Windows using `msvcrt` to convert
        // named pipes into file descriptors for `os.open()`. Rust does not have the
        // same abstraction, instead forcing us into unsafe code with the `libc` crate
        // for similar behavior.
        Err(PyNotImplementedError::new_err(
            "Stream context manager not yet supported on Windows.",
        ))
    }

    /// Set a prefix for each message.
    fn set_prefix(&mut self, prefix: String) {
        self.prefix = Some(prefix);
    }

    /// Clear the current prefix.
    fn clear_prefix(&mut self) {
        self.prefix = None;
    }
}

impl Emitter {
    /// Stop the printing infrastructure and print a final message to see the logs.
    fn finish(&mut self) -> PyResult<()> {
        crate::printer::printer().stop()?;
        Ok(())
    }

    /// Set up the infrastructure to capture Python logging events
    /// and redirect them into the emitter.
    fn setup_external_log_capture(
        py: Python<'_>,
        verbosity: Verbosity,
        streaming_brief: bool,
    ) -> PyResult<Option<Py<PyAny>>> {
        let log_handler = LogListener::new(py, verbosity, streaming_brief)?;

        // Instantiate the Python wrapper for log handling
        let py_log_handler = py
            .import("craft_cli._logs")?
            .getattr("setup_logging_capture")?
            .call1((log_handler,))?;

        Ok(Some(py_log_handler.unbind()))
    }

    /// Apply the current prefix to a message, if any.
    fn apply_prefix(&self, message: &mut Message) {
        if let Some(prefix) = &self.prefix {
            let text = format!("{prefix} :: {}", message.text);
            message.text = text;
        }
    }
}

impl Drop for Emitter {
    fn drop(&mut self) {
        if let Err(e) = crate::printer::printer().stop()
            && !thread::panicking()
        {
            eprintln!("Cannot stop printer: {e:?}");
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
