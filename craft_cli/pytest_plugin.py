# Copyright 2022 Canonical Ltd.
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

"""Different fixtures for easier testability of Craft CLI services."""

import contextlib
import os
import pathlib
import re
import tempfile
from unittest.mock import call

import pytest

from craft_cli import messages


@pytest.fixture(autouse=True)
def init_emitter(monkeypatch):
    """Ensure emit is always clean, and initted (in test mode).

    Note that the `init` is done in the current instance that all modules already
    acquired.
    """
    # init with a custom log filepath so user directories are not involved here; note that
    # we're not using pytest's standard tmp_path as Emitter would write logs there, and in
    # effect we would be polluting that temporary directory (potentially messing with
    # tests, that may need that empty), so we use another one.
    temp_fd, temp_logfile = tempfile.mkstemp(prefix="emitter-logs")
    os.close(temp_fd)
    temp_logfile = pathlib.Path(temp_logfile)

    monkeypatch.setattr(messages, "TESTMODE", True)
    messages.emit.init(
        messages.EmitterMode.QUIET, "test-emitter", "Hello world", log_filepath=temp_logfile
    )
    yield
    # end machinery (just in case it was not ended before; note it's ok to "double end")
    messages.emit.ended_ok()
    temp_logfile.unlink()


class RegexComparingText(str):
    """A string that compares for equality using regex.match."""

    def __eq__(self, other):
        return bool(re.match(self, other, re.DOTALL))

    def __hash__(self):
        return str.__hash__(self)


class RecordingEmitter:
    """Record what is shown using the emitter and provide a nice API for tests."""

    def __init__(self):
        self.interactions = []
        self.paused = False

    @contextlib.contextmanager
    def pause(self):
        """Mimics the pause context manager, storing the state to simplify tests."""
        self.paused = True
        try:
            yield
        finally:
            self.paused = False

    def record(self, method_name, args, kwargs):
        """Record the method call and its specific parameters."""
        self.interactions.append(call(method_name, *args, **kwargs))

    def _check(self, expected_text, method_name, regex, **kwargs):
        """Really verify messages."""
        if regex:
            expected_text = RegexComparingText(expected_text)
        expected_call = call(method_name, expected_text, **kwargs)
        for stored_call in self.interactions:
            if stored_call == expected_call:
                return stored_call.args[1]
        raise AssertionError(f"Expected call {expected_call} not found in {self.interactions}")

    def assert_message(self, expected_text, intermediate=None, regex=False):
        """Check the 'message' method was properly used."""
        if intermediate is None:
            return self._check(expected_text, "message", regex)
        else:
            return self._check(expected_text, "message", regex, intermediate=intermediate)

    def assert_progress(self, expected_text, regex=False):
        """Check the 'progress' method was properly used."""
        return self._check(expected_text, "progress", regex)

    def assert_trace(self, expected_text, regex=False):
        """Check the 'trace' method was properly used."""
        return self._check(expected_text, "trace", regex)

    def assert_messages(self, texts):
        """Check the list of messages (this is helper for a common case of commands results)."""
        self.assert_interactions([call("message", text) for text in texts])

    def assert_interactions(self, expected_call_list):
        """Check that the expected call list happen at some point between all stored calls.

        If None is passed, asserts that no message was emitted.
        """
        if expected_call_list is None:
            if self.interactions:
                show_interactions = "\n".join(map(str, self.interactions))
                raise AssertionError("Expected no call but really got:\n" + show_interactions)
            return

        for pos, stored_call in enumerate(self.interactions):
            if stored_call == expected_call_list[0]:
                break
        else:
            pos = 0

        stored = self.interactions[pos: pos + len(expected_call_list)]
        assert stored == expected_call_list


class RecordingProgresser:
    def __init__(self, recording_emitter):
        self.recording_emitter = recording_emitter

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False  # do not consume any exception

    def advance(self, *a, **k):
        """Record the advance usage."""
        self.recording_emitter.record("advance", a, k)


@pytest.fixture
def emitter(monkeypatch):
    """Helper to test everything that was shown using craft-cli Emitter."""
    recording_emitter = RecordingEmitter()
    for method_name in ("message", "progress", "trace"):
        monkeypatch.setattr(
            messages.emit,
            method_name,
            lambda *a, method_name=method_name, **k: recording_emitter.record(method_name, a, k),
        )

    # progress bar is special, because it also needs to return a context manager with
    # something that will record progress calls
    def fake_progress_bar(*a, **k):
        recording_emitter.record("progress_bar", a, k)
        return RecordingProgresser(recording_emitter)

    monkeypatch.setattr(messages.emit, "progress_bar", fake_progress_bar)

    # pause is also special, as it's specifically implemented in the recording emitter
    monkeypatch.setattr(messages.emit, "pause", recording_emitter.pause)

    return recording_emitter
