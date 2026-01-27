//! Utilities for testing
#![cfg(test)]

use pyo3::{PyErr, PyTypeInfo, Python};
use regex::Regex;

pub fn assert_error_type<T: PyTypeInfo>(err: &PyErr) {
    Python::attach(|py| assert!(err.is_instance_of::<T>(py)));
}

pub fn assert_error_contents(err: &PyErr, re: &str) {
    let re: Regex = re.try_into().expect("Could not be parsed as regex!");

    Python::attach(|py| {
        let value = err.value(py).to_string();
        assert!(re.is_match(&value));
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use pyo3::exceptions::PyValueError;

    mod assert_error_type {
        use super::*;

        #[test]
        fn basic() {
            let err = PyValueError::new_err("Oh no!");

            assert_error_type::<PyValueError>(&err);
        }
    }

    mod assert_error_contents {
        use super::*;

        #[test]
        fn basic() {
            let err = PyValueError::new_err("Oh no!");

            assert_error_contents(&err, "Oh no!");
        }
    }
}
