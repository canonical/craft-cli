#![warn(
    clippy::pedantic,
    clippy::mem_forget,
    clippy::allow_attributes,
    clippy::dbg_macro,
    clippy::clone_on_ref_ptr,
    clippy::missing_docs_in_private_items
)]
// Specifically allow wildcard imports as they are a very common pattern for enum
// matching and module setup
#![allow(clippy::wildcard_imports, clippy::enum_glob_use)]

//! Craft CLI
//!
//! The perfect foundation for your CLI situation.

use pyo3::pymodule;

mod craft_cli_utils;
mod emitter;
mod printer;
mod test_utils;
mod utils;

/// A Python module implemented in Rust.
#[pymodule]
mod _rs {
    #[pymodule_export]
    use crate::craft_cli_utils::utils;

    #[pymodule_export]
    use crate::emitter::emitter;
}
