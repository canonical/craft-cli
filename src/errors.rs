use pyo3::{
    Bound, PyResult, PyTypeInfo as _,
    exceptions::PyBaseException,
    pyclass, pymethods, pymodule,
    types::{PyAnyMethods, PyDict, PyString, PySuper, PyTypeMethods},
};

#[derive(PartialEq)]
#[pyclass(extends = PyBaseException, subclass, get_all, set_all, eq)]
pub struct CraftError {
    pub message: String,
    pub details: Option<String>,
    pub resolution: Option<String>,
    pub docs_url: Option<String>,
    pub docs_slug: Option<String>,
    pub show_logpath: bool,
    pub retcode: u8,
}

#[pymethods]
impl CraftError {
    #[new]
    #[pyo3(signature = (
        message,
        *,
        details = None,
        resolution = None,
        docs_url = None,
        docs_slug = None,
        show_logpath = true,
        retcode = 1
    ))]
    fn new(
        message: String,
        details: Option<String>,
        resolution: Option<String>,
        docs_url: Option<String>,
        docs_slug: Option<String>,
        show_logpath: bool,
        retcode: u8,
    ) -> Self {
        Self {
            message,
            details,
            resolution,
            docs_url,
            docs_slug,
            show_logpath,
            retcode,
        }
    }

    #[pyo3(name = "__init__", signature = (_message, **_kwargs))]
    fn init(
        slf: &Bound<'_, Self>,
        _message: &Bound<'_, PyString>,
        _kwargs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        // See https://pyo3.rs/main/class.html#initializer for an explanation on why this method
        // needs to exist.
        // Call "super(self.__class__, self).__init__()"
        PySuper::new(&PyBaseException::type_object(slf.py()), slf)?.call_method0("__init__")?;
        Ok(())
    }

    #[pyo3(name = "__repr__")]
    fn repr(slf: &Bound<'_, Self>) -> PyResult<String> {
        Ok(format!(
            "{}({:?})",
            slf.get_type().qualname()?,
            slf.borrow().message
        ))
    }

    #[pyo3(name = "__str__")]
    fn str(&self) -> String {
        self.message.clone()
    }
}

#[pymodule(submodule)]
pub mod errors {
    use crate::utils::fix_imports;
    use pyo3::types::PyModule;
    use pyo3::{Bound, PyResult};

    #[pymodule_export]
    use super::CraftError;

    #[pymodule_init]
    fn init(m: &Bound<'_, PyModule>) -> PyResult<()> {
        fix_imports(m, "craft_cli._rs.errors")
    }
}
