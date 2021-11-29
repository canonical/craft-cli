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
