//! Utility functions for Craft CLI

use pyo3::pymodule;

/// Utility functions for Craft CLI
#[pymodule(submodule)]
pub mod utils {
    use pyo3::{Bound, PyResult, exceptions::PyValueError, pyfunction, types::PyModule};

    use crate::utils::fix_imports;

    /// Convert a collection of values into a string that lists the values.
    #[pyfunction]
    #[pyo3(signature = (values, conjunction = "and"))]
    fn humanize_list(values: Vec<String>, conjunction: Option<&str>) -> PyResult<String> {
        let conjunction = conjunction.unwrap_or("and");
        match values.as_slice() {
            [] => Err(PyValueError::new_err("Cannot humanize empty list")),
            [_] => Ok(values
                .into_iter()
                .next()
                .expect("Size checked by match arm")),
            [start, end] => Ok(format!("{start} {conjunction} {end}")),
            [start @ .., end] => {
                let start = start.join(", ");
                Ok(format!("{start}, {conjunction} {end}",))
            }
        }
    }

    /// Fix syspath for easier importing in Python.
    #[pymodule_init]
    fn init(m: &Bound<'_, PyModule>) -> PyResult<()> {
        fix_imports(m, "craft_cli._rs.utils")
    }
}
