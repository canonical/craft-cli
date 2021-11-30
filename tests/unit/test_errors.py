import pytest

from craft_cli.errors import CraftError


def test_crafterror_is_comparable():
    a = CraftError("foo")
    b = CraftError("foo")

    assert a == b


def test_crafterror_is_different():
    a = CraftError("foo")
    b = CraftError("bar")

    assert a != b


def test_crafterror_does_not_compare_to_other_exception():
    a = CraftError("foo")
    b = ValueError("foo")

    assert a != b


@pytest.mark.parametrize(
    "argument_name",
    [
        "details",
        "resolution",
        "docs_url",
        "reportable",
        "retcode",
    ],
)
def test_compare_crafterror_with_different_attribute_values(argument_name):
    a = CraftError("message")
    b = CraftError("message")
    setattr(a, argument_name, "foo")
    setattr(b, argument_name, "bar")

    assert a != b


@pytest.mark.parametrize(
    "argument_name",
    [
        "details",
        "resolution",
        "docs_url",
        "reportable",
        "retcode",
    ],
)
def test_compare_crafterror_with_identical_attribute_values(argument_name):
    a = CraftError("message")
    b = CraftError("message")
    setattr(a, argument_name, "foo")
    setattr(b, argument_name, "foo")

    assert a == b
