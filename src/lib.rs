//! Craft CLI
//!
//! The perfect foundation for your CLI situation.

use pyo3::pymodule;

mod craft_cli_utils;
mod emitter;
mod errors;
mod logs;
mod printer;
mod progress;
mod streams;
mod test_utils;
mod utils;

/// A Python module implemented in Rust.
#[pymodule(name = "_rs")]
mod craft_cli_extensions {
    #[pymodule_export]
    use crate::craft_cli_utils::utils;

    #[pymodule_export]
    use crate::emitter::emitter;

    #[pymodule_export]
    use crate::logs::LogListener;

    #[pymodule_export]
    use crate::errors::errors;
}
