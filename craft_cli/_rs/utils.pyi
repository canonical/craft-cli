from collections.abc import Iterable

def humanize_list(values: Iterable[object], *, conjunction: str = "and") -> str:
    """Convert a collection of values into a string that lists the values."""
