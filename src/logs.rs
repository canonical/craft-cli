use std::cmp::Ordering;

use pyo3::{
    Bound, Py, PyAny, PyResult, Python,
    basic::CompareOp,
    intern, pyclass, pymethods,
    types::{PyAnyMethods, PyInt},
};

use crate::{
    emitter::Verbosity,
    printer::{Message, Target},
    utils,
};

#[pyclass]
pub struct LogListener {
    /// A cached reference to the logging module to avoid re-importing
    /// on each run of [`emit`][LogListener::emit]
    debug_level: Py<PyInt>,

    verbosity: Verbosity,

    streaming_brief: bool,
}

#[pymethods]
impl LogListener {
    fn emit(&mut self, py: Python<'_>, record: &Bound<'_, PyAny>) -> PyResult<()> {
        let levelno = record.getattr(intern!(py, "levelno"))?;

        // If the log record is a DEBUG level message or more verbose, and we aren't
        // in trace mode, exit early as we definitely will not log.
        if levelno.compare(&self.debug_level)? == Ordering::Less
            && !matches!(self.verbosity, Verbosity::Trace)
        {
            return Ok(());
        }

        // Call `record.getMessage()` from Python and parse it into a Rust string
        let mut text: String = record.call_method0(intern!(py, "getMessage"))?.extract()?;
        if matches!(self.verbosity, Verbosity::Debug | Verbosity::Trace) {
            text = utils::apply_timestamp(&text).into();
        }
        let target = self.decide_target(&levelno)?;

        let message = Message {
            text,
            target,
            model: crate::printer::MessageType::Debug,
        };

        crate::printer::printer().send(message)?;
        Ok(())
    }
}

impl LogListener {
    pub fn new(py: Python<'_>, verbosity: Verbosity, streaming_brief: bool) -> PyResult<Self> {
        Ok(Self {
            debug_level: py.import("logging")?.getattr("DEBUG")?.extract()?,
            verbosity,
            streaming_brief,
        })
    }

    /// Determine where a log record should be sent.
    ///
    /// This is done based on the current verbosity level, the log level of the log record,
    /// and what Python's logging library uses to denote "debug" level messages.
    fn decide_target(&self, levelno: &Bound<'_, PyAny>) -> PyResult<Option<Target>> {
        // For trace mode, we just always log
        if matches!(self.verbosity, Verbosity::Trace) {
            return Ok(Some(Target::Stderr));
        }

        let comp_op = match self.verbosity {
            Verbosity::Quiet => return Ok(None),
            Verbosity::Brief if !self.streaming_brief => return Ok(None),
            Verbosity::Verbose | Verbosity::Brief => CompareOp::Gt,
            Verbosity::Debug => CompareOp::Ge,
            Verbosity::Trace => unreachable!("Checked above"),
        };

        let should_log = levelno
            .rich_compare(&self.debug_level, comp_op)?
            .is_truthy()?;

        match should_log {
            true => Ok(Some(Target::Stderr)),
            false => Ok(None),
        }
    }
}
