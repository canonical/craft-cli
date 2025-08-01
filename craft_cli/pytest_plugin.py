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

"""Different fixtures for easier testability of Craft CLI services."""

from __future__ import annotations

import contextlib
import re
from collections.abc import Generator
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Any, Literal
from unittest.mock import call

import pytest
from typing_extensions import Self

from craft_cli import messages, printer

if TYPE_CHECKING:
    from unittest.mock import _Call  # type: ignore[reportPrivateUsage]


@pytest.fixture(autouse=True)
def init_emitter(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """Ensure ``emit`` is always clean, and initiated (in test mode).

    Note that the ``init`` is done in the current instance that all modules already
    acquired.

    This is an "autouse" fixture, so it just works, no need to declare it in your tests.
    """
    # initiate with a custom log filepath so user directories are not involved here; note that
    # we're not using pytest's standard tmp_path as Emitter would write logs there, and in
    # effect we would be polluting that temporary directory (potentially messing with
    # tests, that may need that empty), so we use another one
    with NamedTemporaryFile("w", prefix="emitter-logs") as tmp_logfile:
        monkeypatch.setattr(messages, "TESTMODE", True)
        monkeypatch.setattr(printer, "TESTMODE", True)
        messages.emit.init(
            messages.EmitterMode.QUIET,
            "test-emitter",
            "Hello world",
            log_filepath=Path(tmp_logfile.name),
        )
        yield
    # end machinery (just in case it was not ended before; note it's ok to "double end")
    messages.emit.ended_ok()


class _RegexComparingText(str):
    """A string that compares for equality using regex.match."""

    def __eq__(self, other: object) -> bool:
        return bool(re.match(self, str(other), re.DOTALL))

    def __hash__(self) -> int:
        return str.__hash__(self)


class RecordingEmitter:
    """Record what is shown using the emitter and provide a nice API for tests.

    This class is NOT meant to be used directly, please use the ``emitter`` fixture instead
    which provides an instance of this class with context properly set up.
    """

    def __init__(self) -> None:
        self.interactions: list[_Call] = []
        self.paused = False

    @contextlib.contextmanager
    def pause(self) -> Generator[None]:
        """Mimics the pause context manager, storing the state to simplify tests."""
        self.paused = True
        try:
            yield
        finally:
            self.paused = False

    def record(self, method_name: str, args: Any, kwargs: dict[str, Any]) -> None:
        """Record the method call and its specific parameters."""
        self.interactions.append(call(method_name, *args, **kwargs))

    def _check(
        self,
        expected_text: str,
        method_name: str,
        regex: bool,  # noqa: FBT001
        **kwargs: Any,
    ) -> Any:
        """Really verify messages."""
        if regex:
            expected_text = _RegexComparingText(expected_text)
        expected_call = call(method_name, expected_text, **kwargs)
        for stored_call in self.interactions:
            if stored_call == expected_call:
                return stored_call.args[1]
        raise AssertionError(
            f"Expected call {expected_call} not found in {self.interactions}"
        )

    def assert_message(
        self,
        expected_text: str,
        regex: bool = False,  # noqa: FBT001
    ) -> Any:
        """Check the 'message' method was properly used.

        It verifies that the method was called at least once with the expected text.

        If 'regex' is True, the expected text will be used as a regular expression.
        """
        return self._check(expected_text, "message", regex)

    def assert_progress(
        self,
        expected_text: str,
        permanent: bool | None = None,  # noqa: FBT001
        regex: bool = False,  # noqa: FBT001
    ) -> Any:
        """Check the 'progress' method was properly used.

        It verifies that the method was called at least once with the expected text (with
        the given 'permanent' flag).

        If 'regex' is True, the expected text will be used as a regular expression.
        """
        if permanent is None:
            result = self._check(expected_text, "progress", regex)
        else:
            result = self._check(expected_text, "progress", regex, permanent=permanent)
        return result

    def assert_verbose(
        self,
        expected_text: str,
        regex: bool = False,  # noqa: FBT001
    ) -> Any:
        """Check the 'verbose' method was properly used.

        It verifies that the method was called at least once with the expected text.

        If 'regex' is True, the expected text will be used as a regular expression.
        """
        return self._check(expected_text, "verbose", regex)

    def assert_warning(self, expected_text: str, *, regex: bool = False) -> Any:
        """Check the 'warning' method was properly used.

        It verifies that the method was called at least once with the expected text.

        If 'regex' is True, the expected text will be used as a regular expression.
        """
        return self._check(expected_text, "warning", regex)

    def assert_debug(
        self,
        expected_text: str,
        regex: bool = False,  # noqa: FBT001
    ) -> Any:
        """Check the 'debug' method was properly used.

        It verifies that the method was called at least once with the expected text.

        If 'regex' is True, the expected text will be used as a regular expression.
        """
        return self._check(expected_text, "debug", regex)

    def assert_trace(
        self,
        expected_text: str,
        regex: bool = False,  # noqa: FBT001
    ) -> Any:
        """Check the 'trace' method was properly used.

        It verifies that the method was called at least once with the expected text.

        If 'regex' is True, the expected text will be used as a regular expression.
        """
        return self._check(expected_text, "trace", regex)

    def assert_messages(self, texts: list[str]) -> None:
        """Check that the 'message' method was called several times with the given texts.

        This is helper for a common case that happen in multiline commands results
        where 'message' is called several times.
        """
        self.assert_interactions([call("message", text) for text in texts])

    def assert_interactions(self, expected_call_list: list[_Call] | None) -> None:
        """Check that the expected call list happen at some point between all stored calls.

        If None is passed, asserts that no message was emitted.
        """
        if expected_call_list is None:
            if self.interactions:
                show_interactions = "\n".join(map(str, self.interactions))
                raise AssertionError(
                    "Expected no call but really got:\n" + show_interactions
                )
            return

        for _pos, stored_call in enumerate(self.interactions):
            if stored_call == expected_call_list[0]:
                pos = _pos
                break
        else:
            pos = 0

        end_pos = pos + len(expected_call_list)
        stored = self.interactions[pos:end_pos]
        assert stored == expected_call_list


class _RecordingProgresser:
    def __init__(self, recording_emitter: RecordingEmitter) -> None:
        self.recording_emitter = recording_emitter

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc_info: object) -> Literal[False]:
        return False  # do not consume any exception

    def advance(self, *a: Any, **k: Any) -> None:
        """Record the advance usage."""
        self.recording_emitter.record("advance", a, k)


@pytest.fixture
def emitter(monkeypatch: pytest.MonkeyPatch) -> RecordingEmitter:
    """Provide a helper to test everything that was shown using the Emitter."""
    recording_emitter = RecordingEmitter()
    for method_name in ("message", "progress", "verbose", "debug", "trace", "warning"):

        def new_method(*a: Any, method_name: str = method_name, **k: Any) -> None:
            recording_emitter.record(method_name, a, k)

        monkeypatch.setattr(
            messages.emit,
            method_name,
            new_method,
        )

    # progress bar is special, because it also needs to return a context manager with
    # something that will record progress calls
    def fake_progress_bar(*a: Any, **k: Any) -> _RecordingProgresser:
        recording_emitter.record("progress_bar", a, k)
        return _RecordingProgresser(recording_emitter)

    monkeypatch.setattr(messages.emit, "progress_bar", fake_progress_bar)

    # pause is also special, as it's specifically implemented in the recording emitter
    monkeypatch.setattr(messages.emit, "pause", recording_emitter.pause)

    return recording_emitter
