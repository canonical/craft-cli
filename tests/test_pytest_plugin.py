# Copyright 2022-2023 Canonical Ltd.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""Test the fixtures provided by Craft CLI."""

from unittest.mock import call

import pytest
from craft_cli import messages, printer
from craft_cli.errors import CraftCommandError, CraftError
from craft_cli.pytest_plugin import raises_craft_error

# -- tests for the `init_emitter` auto-fixture


def test_initemitter_initiated():
    """The emitter is initiated."""
    assert messages.emit._initiated
    assert not messages.emit._stopped


def test_initemitter_testmode():
    """The messages module is set to test mode."""
    assert messages.TESTMODE is True
    assert printer.TESTMODE is True


def test_initemitter_isolated_tempdir(tmp_path):
    """The pytest's temp path is not polluted with Emitter logs."""
    messages.emit.trace("test")
    assert not list(tmp_path.iterdir())


# -- tests for the `emitter` fixture


def test_emitter_record_message_plain(emitter):
    """Can verify calls to `message`."""
    messages.emit.trace("something else we don't care")
    messages.emit.message("foobar")

    emitter.assert_message("foobar")
    with pytest.raises(AssertionError):
        emitter.assert_message("foo")


def test_emitter_record_progress_simple_plain(emitter):
    """Can verify calls to `progress`."""
    messages.emit.trace("something else we don't care")
    messages.emit.progress("foobar")

    emitter.assert_progress("foobar")
    with pytest.raises(AssertionError):
        emitter.assert_progress("foo")


def test_emitter_record_progress_permanent_plain(emitter):
    """Can verify calls to `progress`."""
    messages.emit.trace("something else we don't care")
    messages.emit.progress("foobar", permanent=True)

    emitter.assert_progress("foobar", permanent=True)
    with pytest.raises(AssertionError):
        emitter.assert_progress("foo", permanent=True)
    with pytest.raises(AssertionError):
        emitter.assert_progress("foobar")


def test_emitter_record_verbose_plain(emitter):
    """Can verify calls to `verbose`."""
    messages.emit.progress("something else we don't care")
    messages.emit.verbose("foobar")

    emitter.assert_verbose("foobar")
    with pytest.raises(AssertionError):
        emitter.assert_verbose("foo")


def test_emitter_record_warning_plain(emitter):
    """Can verify calls to `warning`."""
    messages.emit.progress("something else we don't care")
    messages.emit.warning("foobar")

    emitter.assert_warning("foobar")
    with pytest.raises(AssertionError):
        emitter.assert_warning("foo")


def test_emitter_record_debug_plain(emitter):
    """Can verify calls to `debug`."""
    messages.emit.progress("something else we don't care")
    messages.emit.debug("foobar")

    emitter.assert_debug("foobar")
    with pytest.raises(AssertionError):
        emitter.assert_debug("foo")


def test_emitter_record_trace_plain(emitter):
    """Can verify calls to `trace`."""
    messages.emit.progress("something else we don't care")
    messages.emit.trace("foobar")

    emitter.assert_trace("foobar")
    with pytest.raises(AssertionError):
        emitter.assert_trace("foo")


def test_emitter_record_message_regex(emitter):
    """Can verify calls to `message` using a regex."""
    messages.emit.message("foobar")
    emitter.assert_message("[fx]oo.*", regex=True)


def test_emitter_record_progress_simple_regex(emitter):
    """Can verify calls to `progress` using a regex."""
    messages.emit.progress("foobar")
    emitter.assert_progress("[fx]oo.*", regex=True)


def test_emitter_record_progress_permanent_regex(emitter):
    """Can verify calls to `progress` using a regex."""
    messages.emit.progress("foobar", permanent=True)
    emitter.assert_progress("[fx]oo.*", permanent=True, regex=True)


def test_emitter_record_verbose_regex(emitter):
    """Can verify calls to `verbose` using a regex."""
    messages.emit.verbose("foobar")
    emitter.assert_verbose("[fx]oo.*", regex=True)


def test_emitter_record_debug_regex(emitter):
    """Can verify calls to `debug` using a regex."""
    messages.emit.debug("foobar")
    emitter.assert_debug("[fx]oo.*", regex=True)


def test_emitter_record_trace_regex(emitter):
    """Can verify calls to `trace` using a regex."""
    messages.emit.trace("foobar")
    emitter.assert_trace("[fx]oo.*", regex=True)


def test_emitter_record_progress_bar_ok(emitter):
    """Calls to `progress_bar` are recorded."""
    with messages.emit.progress_bar("title", 20, delta=True) as progress_bar:
        progress_bar.advance(100)
    emitter.assert_interactions(
        [
            call("progress_bar", "title", 20, delta=True),
            call("advance", 100),
        ]
    )


def test_emitter_record_progress_bar_advance_negative(emitter):
    """A negative advance is rejected, matching the real progress bar."""
    with messages.emit.progress_bar("title", 20) as progress_bar:
        with pytest.raises(ValueError, match="cannot be negative"):
            progress_bar.advance(-1)


def test_emitter_record_progress_bar_safe(emitter):
    """Mocking the progress bar context manager does not hide exceptions."""
    with pytest.raises(ValueError):  # noqa: PT011
        with messages.emit.progress_bar("title", 20):
            raise ValueError


def test_emitter_record_pause(emitter):
    """Calls to `pause` are recorded."""
    assert not emitter.paused
    with messages.emit.pause():
        assert emitter.paused
    assert not emitter.paused


def test_emitter_messages(emitter):
    """Can verify several calls to `message`."""
    for result in range(3):  # simulated bunch of results
        messages.emit.message(f"Got: {result}")
    emitter.assert_messages(
        [
            "Got: 0",
            "Got: 1",
            "Got: 2",
        ]
    )


def test_emitter_interactions_positive_complete(emitter):
    """All interactions can be verified, complete."""
    messages.emit.progress("foo")
    messages.emit.trace("bar")
    messages.emit.message("baz")

    emitter.assert_interactions(
        [
            call("progress", "foo"),
            call("trace", "bar"),
            call("message", "baz"),
        ]
    )


def test_emitter_interactions_positive_cross_data(emitter):
    """All interactions can be verified, crossing elements between calls."""
    messages.emit.progress("foo")
    messages.emit.trace("bar")
    messages.emit.message("baz")

    with pytest.raises(AssertionError):
        emitter.assert_interactions(
            [
                call("progress", "bar"),
            ]
        )


def test_emitter_interactions_positive_sequence(emitter):
    """All interactions can be verified, partial sequence."""
    messages.emit.progress("foo")
    messages.emit.trace("bar")
    messages.emit.message("baz")

    emitter.assert_interactions(
        [
            call("trace", "bar"),
            call("message", "baz"),
        ]
    )


def test_emitter_interactions_positive_not_sequence(emitter):
    """All interactions can be verified, parts not in sequence."""
    messages.emit.progress("foo")
    messages.emit.trace("bar")
    messages.emit.message("baz")

    with pytest.raises(AssertionError):
        emitter.assert_interactions(
            [
                call("progress", "foo"),
                call("message", "baz"),
            ]
        )


def test_emitter_interactions_negative(emitter):
    """Can verify no interactions."""
    # nothing emitted!
    emitter.assert_interactions(None)

    messages.emit.trace("something")
    with pytest.raises(AssertionError):
        emitter.assert_interactions(None)


# -- tests for the `raises_craft_error` helper


def test_raises_craft_error_message_only():
    """The message is matched with a regex, like pytest.raises' match."""
    with raises_craft_error(match="Failed to pull"):
        raise CraftError("Failed to pull some source")

    with pytest.raises(AssertionError):
        with raises_craft_error(match="different message"):
            raise CraftError("Failed to pull some source")


def test_raises_craft_error_subclass():
    """The expected exception type is the first argument, like pytest.raises."""
    with raises_craft_error(CraftCommandError, match="boom"):
        raise CraftCommandError("boom", stderr="some stderr")

    # a subclass of the expected type is accepted
    with raises_craft_error(CraftError, match="boom"):
        raise CraftCommandError("boom", stderr="some stderr")

    # a sibling/base that is not the expected subclass is not accepted
    with pytest.raises(CraftError) as err_info:
        with raises_craft_error(CraftCommandError):
            raise CraftError("boom")
    assert not isinstance(err_info.value, CraftCommandError)


def test_raises_craft_error_as_binding():
    """The returned context manager supports the `as` binding, like pytest.raises."""
    with raises_craft_error(match="boom") as err:
        raise CraftError("boom", details="the details", retcode=7)
    assert err.value.details == "the details"
    assert err.value.retcode == 7


@pytest.mark.parametrize(
    ("field", "kwargs", "error_kwargs"),
    [
        ("details", {"details": "network .* down"}, {"details": "network is down"}),
        ("resolution", {"resolution": "try again"}, {"resolution": "please try again"}),
        ("docs_url", {"docs_url": "http://a/b"}, {"docs_url": "http://a/b/c"}),
    ],
)
def test_raises_craft_error_text_fields(field, kwargs, error_kwargs):
    """The extra text fields are matched with re.search."""
    with raises_craft_error(**kwargs):
        raise CraftError("boom", **error_kwargs)


def test_raises_craft_error_retcode_exact():
    """The retcode is matched by exact equality."""
    with raises_craft_error(retcode=2):
        raise CraftError("boom", retcode=2)

    with pytest.raises(AssertionError, match="retcode mismatch"):
        with raises_craft_error(retcode=2):
            raise CraftError("boom", retcode=3)


def test_raises_craft_error_field_mismatch_message():
    """A field mismatch raises an AssertionError naming the field."""
    with pytest.raises(AssertionError, match="details mismatch"):
        with raises_craft_error(details="expected"):
            raise CraftError("boom", details="actual")


def test_raises_craft_error_combined():
    """Several fields can be matched at once."""
    with raises_craft_error(
        CraftCommandError, match="Failed to pull", details="network .* down", retcode=2
    ):
        raise CraftCommandError(
            "Failed to pull some source",
            stderr="cmd output",
            details="network is down",
            retcode=2,
        )


def test_raises_craft_error_wrong_type_propagates():
    """A non-CraftError exception is not swallowed."""
    with pytest.raises(ValueError):  # noqa: PT011
        with raises_craft_error(match="boom"):
            raise ValueError("boom")


def test_raises_craft_error_did_not_raise():
    """Fails if no exception is raised."""
    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
        with raises_craft_error(match="boom"):
            pass
