//! Utility functions for Craft CLI

use pyo3::pymodule;

/// Utility functions for Craft CLI
#[pymodule(submodule)]
pub mod utils {
    use pyo3::{
        Bound, PyResult,
        exceptions::{PyTypeError, PyValueError},
        pyfunction,
        types::{PyAny, PyAnyMethods as _, PyModule, PyTypeMethods as _},
    };

    use crate::utils::fix_imports;

    /// Convert a collection of values into a string that lists the values.
    #[pyfunction]
    #[pyo3(signature = (values, *, conjunction = "and"))]
    fn humanize_list(values: Bound<'_, PyAny>, conjunction: &str) -> PyResult<String> {
        // Check if it's actually iterable at runtime and collect values
        let items: Vec<_> = match values.try_iter() {
            Ok(py_iter) => py_iter
                .into_iter()
                .map(|maybe_item| maybe_item.map(|item| item.to_string()))
                .collect::<Result<_, _>>()?,
            Err(_) => {
                let type_name = values.get_type().name()?;
                return Err(PyTypeError::new_err(format!(
                    "'{type_name}' object is not iterable"
                )));
            }
        };

        match items.as_slice() {
            [] => Err(PyValueError::new_err("Cannot humanize empty list")),
            [_] => Ok(items.into_iter().next().expect("Size checked by match arm")),
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
