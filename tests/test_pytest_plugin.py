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


def test_emitter_record_progress_bar_safe(emitter):
    """Mocking the progress bar context manager does not hide exceptions."""
    with pytest.raises(ValueError):
        with messages.emit.progress_bar("title", 20):
            raise ValueError()


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
