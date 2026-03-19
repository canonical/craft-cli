use std::sync::{Arc, Mutex};

use bon::bon;
use pyo3::{Bound, PyAny, PyErr, PyRefMut, PyResult, pyclass, pymethods, types::PyType};

use crate::{
    printer::{Event, NewProgressBar, Target},
    utils,
};

#[pyclass]
pub struct Progresser {
    bar: Arc<Mutex<indicatif::ProgressBar>>,
    should_timestamp: bool,
}

#[bon]
impl Progresser {
    #[builder]
    pub fn new(
        message: String,
        total: u64,
        units: Option<String>,
        should_timestamp: bool,
        #[builder(required)] target: Option<Target>,
        #[builder(default)] show_eta: bool,
        #[builder(default)] show_progress: bool,
        #[builder(default)] show_percentage: bool,
    ) -> PyResult<Self> {
        let mut template_str = String::from("{msg} [{wide_bar}]");

        if let Some(units) = units {
            match units.as_str() {
                "bytes" => template_str.push_str(" {bytes}/{total_bytes}"),
                _ => {
                    let sanitized_units = units.replace("{", "{{").replace("}", "}}");
                    template_str
                        .push_str(&format!(" {{human_pos}}/{{human_len}} {sanitized_units}"))
                }
            }
        } else if show_progress {
            template_str.push_str(" {human_pos}/{human_len}");
        }

        if show_percentage {
            template_str.push_str(" {percent}%")
        }

        if show_eta {
            template_str.push_str(" ETA: {eta}")
        }

        let style = indicatif::ProgressStyle::with_template(&template_str)
            // This should only fail if the code above created a bad template string for indicatif.
            // See https://docs.rs/indicatif/latest/indicatif/index.html#templates
            .expect("An invalid progress bar was rendered.");

        let bar = Arc::new(Mutex::new(
            indicatif::ProgressBar::with_draw_target(
                Some(total),
                target
                    .map(Target::into)
                    .unwrap_or(indicatif::ProgressDrawTarget::hidden()),
            )
            .with_style(style)
            .with_message(message),
        ));

        crate::printer::printer().send(Event::NewProgressBar(NewProgressBar {
            bar: Arc::clone(&bar),
        }))?;

        Ok(Self {
            bar,
            should_timestamp,
        })
    }
}

#[pymethods]
impl Progresser {
    pub fn tick(&self) -> PyResult<()> {
        crate::printer::printer().send(Event::UpdateProgressBar(1))
    }

    pub fn inc(&self, delta: u64) -> PyResult<()> {
        crate::printer::printer().send(Event::UpdateProgressBar(delta))
    }

    pub fn println(&self, mut text: String) -> PyResult<()> {
        if self.should_timestamp {
            text = utils::apply_timestamp(&text).to_string();
        }
        crate::printer::printer().send(Event::PrintProgressBar(text))
    }

    pub fn progress(&self) -> u64 {
        self.bar
            .lock()
            .expect("Failed to communicate with progress bar")
            .position()
    }

    #[pyo3(name = "__enter__")]
    fn enter(slf: PyRefMut<'_, Self>) -> PyRefMut<'_, Self> {
        slf
    }

    #[pyo3(name = "__exit__")]
    fn exit(
        &mut self,
        exc_type: Option<Bound<'_, PyType>>,
        exc_value: Option<Bound<'_, PyAny>>,
        _traceback: Option<Bound<'_, PyAny>>,
    ) -> PyResult<()> {
        if let (Some(exc_type), Some(exc_value)) = (exc_type, exc_value) {
            crate::printer::printer().send(Event::AbortProgressBar)?;
            let err = PyErr::from_type(exc_type, exc_value.unbind());
            return Err(err);
        }

        crate::printer::printer().send(Event::FinishProgressBar)
    }
}
