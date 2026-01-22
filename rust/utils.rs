//! Internal utils for Craft CLI.

use pyo3::{
    Bound, PyResult, Python,
    types::{PyAnyMethods, PyModule},
};

/// Hack: workaround for [an upstream issue in PyO3](https://github.com/PyO3/pyo3/issues/759)
pub fn fix_imports(m: &Bound<'_, PyModule>, name: &str) -> PyResult<()> {
    Python::attach(|py| py.import("sys")?.getattr("modules")?.set_item(name, m))
}

// This log function is very convenient for development, but may not necessarily always exist
// in live code.
#[allow(unused, clippy::allow_attributes)]
/// Log a message for debugging purposes only.
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

            handle
                .write_all("I hope you find what you are looking for, traveller.\n".as_ref())
                .expect("Couldn't write to debugging log!");

            Mutex::new(handle)
        });
        FILE.lock()
            .unwrap()
            .write_all(format!("{}\n", message.into()).as_ref())
            .expect("Couldn't write to debugging log!");
    }
}
