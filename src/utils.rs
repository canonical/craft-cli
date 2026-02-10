//! Internal utils for Craft CLI.

use std::borrow::Cow;

use pyo3::{
    Bound, PyResult, Python,
    types::{PyAnyMethods, PyModule},
};

/// Hack: workaround for [an upstream issue in PyO3](https://github.com/PyO3/pyo3/issues/759)
pub fn fix_imports(m: &Bound<'_, PyModule>, name: &str) -> PyResult<()> {
    Python::attach(|py| py.import("sys")?.getattr("modules")?.set_item(name, m))
}

/// Apply the timestamp to a message if necessary.
pub fn apply_timestamp(text: &str) -> Cow<'_, str> {
    format!(
        "{} {}",
        jiff::Timestamp::now().strftime("%Y-%m-%d %H:%M:%S%.3f"),
        text
    )
    .into()
}

// This log function is very convenient for development, but may not necessarily always exist
// in live code.
#[allow(unused, clippy::allow_attributes)]
/// Log a message for debugging purposes only.
///
/// All messages will go to `./craft-cli-debug.log`. This file will be created the first time
/// a message attempts to be logged, and will be cleared between runs.
pub fn log(message: impl Into<String>) {
    #[cfg(debug_assertions)]
    {
        use std::{
            fs,
            io::Write as _,
            sync::{LazyLock, Mutex},
        };

        static FILE: LazyLock<Mutex<fs::File>> = LazyLock::new(|| {
            let mut handle = fs::OpenOptions::new()
                .create(true)
                .write(true)
                .truncate(true)
                .open("craft-cli-debug.log")
                .expect("Couldn't open debugging log!");

            writeln!(
                handle,
                "I hope you find what you are looking for, traveller."
            )
            .expect("Cannot write to debugging log");
            Mutex::new(handle)
        });

        writeln!(FILE.lock().unwrap(), "{}", message.into())
            .expect("Cannot write to debugging log");
    }
}
