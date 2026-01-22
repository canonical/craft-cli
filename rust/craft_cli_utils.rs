//! Utility functions for Craft CLI

use pyo3::pymodule;

/// Utility functions for Craft CLI
#[pymodule(submodule)]
pub mod utils {
    use pyo3::{Bound, PyResult, pyfunction, types::PyModule};

    use crate::utils::fix_imports;

    /// Convert a collection of values into a string that lists the values.
    #[pyfunction]
    #[pyo3(signature = (values, conjunction = "and"))]
    fn humanize_list(mut values: Vec<String>, conjunction: Option<&str>) -> String {
        let start = values
            .drain(..values.len() - 1)
            .collect::<Vec<String>>()
            .join(", ");

        let conjunction = conjunction.unwrap_or("and");

        format!(
            "{}, {} {}",
            start,
            conjunction,
            values.first().expect("Guaranteed by drain call above")
        )
    }

    /// Fix syspath for easier importing in Python.
    #[pymodule_init]
    fn init(m: &Bound<'_, PyModule>) -> PyResult<()> {
        fix_imports(m, "craft_cli._rs.utils")
    }
}
