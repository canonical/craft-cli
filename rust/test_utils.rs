//! Utilities for testing
#![cfg(test)]

use std::fmt::Debug;

use pyo3::{PyErr, PyTypeInfo, Python};
use regex::Regex;

pub fn assert_error_type<T: PyTypeInfo>(err: &PyErr) {
    Python::attach(|py| assert!(err.is_instance_of::<T>(py)));
}

pub fn assert_error_contents<R>(err: &PyErr, r#match: R)
where
    // Accept anything that can be converted into Regex
    R: TryInto<Regex>,
    // Should always be true, this is just to please the type checker
    <R as TryInto<Regex>>::Error: Debug,
{
    let re: Regex = r#match.try_into().expect("Could not be parsed as regex!");

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
