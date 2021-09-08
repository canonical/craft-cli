#
# Copyright 2021 Canonical Ltd.
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

"""Tests that check the whole message machinery.

These are "integration" tests in the sense that call the external API and verify final
outputs.

Most of the different cases here mimic the specification table in:

    https://docs.google.com/document/d/1Pe-0ED6db53SmrUGIAgVMzxeCOGJQwsZJWf7jzFSagQ/
"""

import logging
import re
from dataclasses import dataclass

import pytest

from craft_cli import messages
from craft_cli.messages import Emitter, EmitterMode

# the timestamp format (including final separator space)
TIMESTAMP_FORMAT = r"\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d.\d\d\d "

# the greeting sent and logfile, normalized across the tests so we can automatically ignore them
GREETING = "Specific greeting to be ignored"
FAKE_LOGNAME = "testapp-ignored.log"


@pytest.fixture(autouse=True)
def fake_log_filepath(tmp_path, monkeypatch):
    """Provide a fake log filepath, outside of user's appdir."""
    fake_logpath = str(tmp_path / FAKE_LOGNAME)
    monkeypatch.setattr(messages, "get_log_filepath", lambda appname: fake_logpath)


@pytest.fixture(autouse=True)
def fix_terminal_width(monkeypatch):
    """Set a very big terminal width so messages are normally not wrapped."""
    monkeypatch.setattr(messages, "get_terminal_width", lambda: 500)


@pytest.fixture
def logger():
    """Provide a logger with an empty set of handlers."""
    logger = logging.getLogger()
    logger.setLevel(0)
    logger.handlers.clear()
    return logger


@dataclass
class Line:
    """A line that is expected to be in the result."""

    text: str
    permanent: bool = True  # if it should be overwritten by next message or not
    timestamp: bool = False  # if it should be prefixed by a timestamp


def compare_lines(expected_lines, raw_stream):
    """Helper to compare expected lines to what was written to the terminal."""
    width = messages.get_terminal_width()
    if expected_lines:
        assert len(raw_stream) > 0
    assert len(raw_stream) % width == 0, f"Bad length {len(raw_stream)} ({width=}) {raw_stream=!r}"
    args = [iter(raw_stream)] * width
    lines = ["".join(x) for x in zip(*args)]
    if lines and GREETING in lines[0]:
        lines = lines[1:]
    if lines and FAKE_LOGNAME in lines[0]:
        lines = lines[1:]

    assert len(expected_lines) == len(lines), repr(lines)
    for expected, real in zip(expected_lines, lines):
        end_of_line = "\n" if expected.permanent else "\r"
        timestamp = TIMESTAMP_FORMAT if expected.timestamp else ""

        # the timestamp (if should be there), the text to compare, some spaces, and the CR/LN
        template = f"{timestamp}(.*?) *{end_of_line}"
        match = re.match(template, real)
        assert match, f"Line {real!r} didn't match {template!r}"
        assert match.groups()[0] == expected.text


def assert_outputs(capsys, emit, expected_out=None, expected_err=None, expected_log=None):
    """Verify that the outputs are correct according to the expected lines."""
    # check the expected stdout and stderr outputs
    out, err = capsys.readouterr()
    if expected_out is None:
        assert not out
    else:
        compare_lines(expected_out, out)
    if expected_err is None:
        compare_lines([], err)  # this comparison will eliminate the greeting and log path lines
    else:
        compare_lines(expected_err, err)

    # get the logged text, always validating a valid timestamp format at the beginning
    # of each line
    with open(emit.log_filepath, "rt", encoding="utf8") as filehandler:
        log_lines = filehandler.readlines()
    logged_texts = []
    for line in log_lines:
        match = re.match(rf"{TIMESTAMP_FORMAT}(.*)\n", line)
        assert match
        logged_texts.append(match.groups()[0])
    if logged_texts and GREETING in logged_texts[0]:
        logged_texts = logged_texts[1:]

    if expected_log is None:
        assert not logged_texts
    else:
        expected_logged_texts = [x.text for x in expected_log]
        assert expected_logged_texts == logged_texts


@pytest.mark.parametrize("mode", EmitterMode)  # all modes!
def test_01_expected_cmd_result(capsys, mode):
    """Show a simple message, the expected command result."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    emit.message("The meaning of life is 42.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42."),
    ]
    assert_outputs(capsys, emit, expected_out=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_01_intermediate_message_quiet(capsys, mode):
    """Show an intermediate message, in more quiet modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    emit.message("The meaning of life is 42.", intermediate=True)
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42."),
    ]
    assert_outputs(capsys, emit, expected_out=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_01_intermediate_message_verbose(capsys, mode):
    """Show an intermediate message, in more verbose modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    emit.message("The meaning of life is 42.", intermediate=True)
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42.", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_out=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_initial_messages_when_quietish(capsys, mode, monkeypatch, tmp_path):
    """Check the initial messages are sent when setting the mode to more quiet modes."""
    # use different greeting and file logpath so we can actually test them
    different_greeting = "different greeting to not be ignored"
    different_logpath = str(tmp_path / "otherfile.log")
    monkeypatch.setattr(messages, "get_log_filepath", lambda appname: different_logpath)

    emit = Emitter()
    emit.init(EmitterMode.NORMAL, "testapp", different_greeting)
    emit.set_mode(mode)
    emit.message("final message")
    emit.ended_ok()

    expected_out = [
        Line("final message"),
    ]
    expected_log = [
        Line(different_greeting),
        Line("final message"),
    ]
    assert_outputs(capsys, emit, expected_out=expected_out, expected_log=expected_log)


def test_initial_messages_when_verbose(capsys, tmp_path, monkeypatch):
    """Check the initial messages are sent when setting the mode to VERBOSE."""
    # use different greeting and file logpath so we can actually test them
    different_greeting = "different greeting to not be ignored"
    different_logpath = str(tmp_path / "otherfile.log")
    monkeypatch.setattr(messages, "get_log_filepath", lambda appname: different_logpath)

    emit = Emitter()
    emit.init(EmitterMode.NORMAL, "testapp", different_greeting)
    emit.set_mode(EmitterMode.VERBOSE)
    emit.message("final message")
    emit.ended_ok()

    expected_out = [
        Line("final message"),
    ]
    expected_err = [
        Line(different_greeting, timestamp=True),
        Line(f"Logging execution to '{different_logpath}'", timestamp=True),
    ]
    expected_log = [
        Line(different_greeting),
        Line("final message"),
    ]
    assert_outputs(
        capsys,
        emit,
        expected_out=expected_out,
        expected_err=expected_err,
        expected_log=expected_log,
    )


def test_initial_messages_when_trace(capsys, tmp_path, monkeypatch):
    """Check the initial messages are sent when setting the mode to TRACE."""
    # use different greeting and file logpath so we can actually test them
    different_greeting = "different greeting to not be ignored"
    different_logpath = str(tmp_path / "otherfile.log")
    monkeypatch.setattr(messages, "get_log_filepath", lambda appname: different_logpath)

    emit = Emitter()
    emit.init(EmitterMode.NORMAL, "testapp", different_greeting)
    emit.set_mode(EmitterMode.TRACE)
    emit.message("final message")
    emit.ended_ok()

    expected_out = [
        Line("final message"),
    ]
    expected_err = [
        Line(different_greeting, timestamp=True),
        Line(f"Logging execution to '{different_logpath}'", timestamp=True),
    ]
    expected_log = [
        Line(different_greeting),
        Line("final message"),
    ]
    assert_outputs(
        capsys,
        emit,
        expected_out=expected_out,
        expected_err=expected_err,
        expected_log=expected_log,
    )
