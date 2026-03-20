//! The Emitter class and its associated helpers.

use std::{path::PathBuf, thread};

use pyo3::{
    Bound, Py, PyAny, PyResult, Python, pyclass, pymethods, pymodule,
    types::{PyAnyMethods as _, PyType},
};

use crate::{
    logs::LogListener,
    printer::{Event, Target, Text},
    progress::Progresser,
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

    /// Brief output. Most messages should be ephemeral and all debugging
    /// message types should be skipped.
    #[pyo3(name = "BRIEF")]
    Brief,

    /// Verbose mode. All messages should be persistent and some debugging
    /// message types are output.
    #[pyo3(name = "VERBOSE")]
    Verbose,

    /// Debug mode. Almost all messages are printed and persistent, except
    /// for highly verbose messages from external libraries.
    #[pyo3(name = "DEBUG")]
    Debug,

    /// Trace mode. Absolutely all messages are printed and persistent.
    #[pyo3(name = "TRACE")]
    Trace,
}

/// The Emitter is the primary entry point of Craft CLI for message printing and
/// logging.
///
/// The act of "emitting", in context of the Emitter, is the handling of a given
/// message event. For a given message, depending on the verbosity level and the
/// sort of message sent, this could mean as little as simply sending it to the log
/// file. It could also mean as much as finishing up a spinning "in-progress"
/// action, rendering its time elapsed over that line, prepending a timestamp to the
/// new message, and sending it to both the terminal and the log file.
#[pyclass]
struct Emitter {
    /// The original filepath of the log file.
    log_filepath: String,

    // Used by `report_error` on the Python side, which was left in Python due to
    // the retrieved errors all still being in Python.
    #[expect(unused)]
    /// The base URL for error messages.
    docs_base_url: Option<String>,

    /// The verbosity mode.
    verbosity: Verbosity,

    /// The greeting the emitter was started with.
    greeting: String,

    /// A handle on log handling.
    _log_handle: Option<Py<PyAny>>,

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
    /// The supplied `greeting` is emitted upon instantiation. `docs_base_url` is used
    /// as a prefix for documentation slugs supplied by certain error types.
    ///
    /// ## Streaming Brief
    ///
    /// If [Verbosity::Brief] is set, "streaming brief" mode is used to provide extra
    /// information without flooding the terminal session. Otherwise excessively verbose
    /// messages will be emitted ephemerally, being overwritten by the next message.
    ///
    /// This is often a good default for applications, as it gives feedback about progress
    /// without inundating a user with excessive information.
    #[new]
    #[pyo3(signature = (verbosity, log_filepath, greeting, *, docs_base_url = None, streaming_brief = false))]
    fn new(
        py: Python<'_>,
        verbosity: Verbosity,
        log_filepath: String,
        greeting: String,
        docs_base_url: Option<&str>,
        streaming_brief: bool,
    ) -> PyResult<Self> {
        crate::printer::printer().init_logger(&log_filepath, &greeting)?;

        let docs_base_url = docs_base_url.map(|url| url.trim_end_matches('/').to_string());
        let _log_handle = Self::setup_external_log_capture(py, verbosity, streaming_brief)?;
        Ok(Self {
            log_filepath,
            docs_base_url,
            verbosity,
            greeting,
            _log_handle,
            streaming_brief,
        })
    }

    /// Create a log filepath from an app name as an easy default.
    #[classmethod]
    fn log_filepath_from_name(_cls: &Bound<'_, PyType>, app_name: &str) -> PathBuf {
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

        base_dir.join(log_filepath).with_added_extension("log")
    }

    /// Get the current verbosity level.
    fn get_verbosity(&self) -> Verbosity {
        self.verbosity
    }

    /// Set the verbosity level.
    fn set_verbosity(&mut self, new: Verbosity) -> PyResult<()> {
        self.verbosity = new;

        if new >= Verbosity::Verbose {
            let messages = [
                self.greeting.clone(),
                format!("Logging execution to {}", self.log_filepath),
            ];
            for message in messages {
                crate::printer::printer().send(Event::Text(Text {
                    message,
                    target: Some(Target::Stderr),
                    permanent: true,
                }))?;
            }
        }

        Ok(())
    }

    /// Send a verbose message.
    ///
    /// Useful for providing more information to the user that isn't particularly
    /// helpful for "regular use".
    fn verbose(&mut self, text: &str) -> PyResult<()> {
        let timestamped = utils::apply_timestamp(text);

        let (maybe_timestamped, target) = match self.verbosity {
            Verbosity::Brief | Verbosity::Quiet => (text, None),
            Verbosity::Verbose => (text, Some(Target::Stderr)),
            Verbosity::Debug | Verbosity::Trace => (timestamped.as_ref(), Some(Target::Stderr)),
        };
        let text = maybe_timestamped.to_string();

        let event = Event::Text(Text {
            message: text,
            target,
            permanent: true,
        });

        crate::printer::printer().send(event)?;
        Ok(())
    }

    /// Send a debug message.
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
        let message = timestamped.to_string();

        let event = Event::Text(Text {
            message,
            target,
            permanent: true,
        });

        crate::printer::printer().send(event)?;
        Ok(())
    }

    /// Send a trace message.
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
        let message = timestamped.to_string();

        let event = Event::Text(Text {
            message,
            target,
            permanent: true,
        });

        crate::printer::printer().send(event)?;
        Ok(())
    }

    /// Send a progress message.
    ///
    /// This is normally used to present several related messages relaying how
    /// a task is going.
    ///
    /// These messages will be overwritten by the next line. If a progress message
    /// is important enough that it shouldn't be overwritten by the next ones, set
    /// `permanent` to `true`.
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

        let message = maybe_timestamped.to_owned();

        let event = Event::Text(Text {
            message,
            target,
            permanent,
        });

        crate::printer::printer().send(event)?;

        // If we're in streaming brief mode and the last message was ephemeral, set this message as the new prefix
        if matches!(self.verbosity, Verbosity::Brief) && !permanent && self.streaming_brief {
            self.set_prefix(text.to_string());
        }

        Ok(())
    }

    /// Send a message.
    ///
    /// Ideally used as the final message in a sequence to show a result, as it
    /// goes to stdout unlike other message types.
    fn message(&mut self, text: String) -> PyResult<()> {
        // A message-type emission finalizes the current task and shouldn't have a prefix
        self.clear_prefix();

        let target = match self.verbosity {
            Verbosity::Quiet => None,
            _ => Some(Target::Stdout),
        };

        let event = Event::Text(Text {
            message: text,
            target,
            permanent: true,
        });

        crate::printer::printer().send(event)?;
        Ok(())
    }

    /// Show a warning message.
    ///
    /// By default, messages will be prefixed with "WARNING: ". An alternative prefix
    /// can be provided via the `prefix` parameter.
    #[pyo3(signature = (text, *, prefix = "WARNING: "))]
    fn warning(&mut self, text: &str, prefix: &str) -> PyResult<()> {
        let prefixed = format!("{}{}", prefix, text);
        let timestamped = utils::apply_timestamp(&prefixed);

        let (maybe_timestamped, target) = match self.verbosity {
            Verbosity::Quiet => (prefixed.as_str(), None),
            Verbosity::Debug | Verbosity::Trace => (timestamped.as_ref(), Some(Target::Stderr)),
            _ => (prefixed.as_str(), Some(Target::Stderr)),
        };
        let message = maybe_timestamped.to_string();

        let event = Event::Text(Text {
            message,
            target,
            permanent: true,
        });

        crate::printer::printer().send(event)?;
        Ok(())
    }

    /// Render an incremental progress bar.
    #[pyo3(signature = (
        text,
        total,
        *,
        units = None,
        show_eta = false,
        show_progress = false,
        show_percentage = false
    ))]
    fn progress_bar(
        &mut self,
        text: String,
        total: u64,
        units: Option<String>,
        show_eta: bool,
        show_progress: bool,
        show_percentage: bool,
    ) -> PyResult<Progresser> {
        let target = if self.verbosity != Verbosity::Debug {
            Some(Target::Stderr)
        } else {
            None
        };

        Progresser::builder()
            .message(text)
            .total(total)
            .maybe_units(units)
            .show_eta(show_eta)
            .show_progress(show_progress)
            .show_percentage(show_percentage)
            .target(target)
            .should_timestamp(self.verbosity >= Verbosity::Debug)
            .build()
    }

    /// Stop gracefully.
    fn ended_ok(&mut self) -> PyResult<()> {
        self.finish()
    }

    /// Open a stream context manager to redirect output to a different stream.
    #[cfg(unix)]
    #[pyo3(signature = (prefix = None))]
    fn open_stream(&self, prefix: Option<String>) -> StreamHandle {
        if let Some(pref) = prefix {
            self.set_prefix(pref);
        }
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
    fn set_prefix(&self, prefix: String) {
        crate::printer::printer().set_prefix(prefix);
    }

    /// Clear the current prefix.
    fn clear_prefix(&self) {
        crate::printer::printer().clear_prefix();
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
