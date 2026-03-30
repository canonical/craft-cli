import pytest
from craft_cli.utils import humanize_list


def test_humanize_list_single_item():
    """A single value should be returned unchanged."""
    assert humanize_list(["a"]) == "a"


def test_humanize_list_two_items():
    """Two values should be joined without a serial comma."""
    assert humanize_list(["a", "b"]) == "a and b"


def test_humanize_list_three_items():
    """Three values should include the serial comma."""
    assert humanize_list(["a", "b", "c"]) == "a, b, and c"


def test_humanize_list_longer_list():
    """Lists longer than three items should format correctly."""
    assert humanize_list(["a", "b", "c", "d"]) == "a, b, c, and d"


def test_humanize_list_custom_conjunction():
    """Custom conjunctions should be respected."""
    assert humanize_list(["a", "b"], conjunction="or") == "a or b"


def test_humanize_list_strings_with_spaces():
    """Values containing spaces should not affect formatting."""
    assert humanize_list(["foo", "bar baz"]) == "foo and bar baz"


def test_humanize_list_empty_list_raises():
    """The current implementation raises IndexError on empty input."""
    with pytest.raises(IndexError):
        humanize_list([])
