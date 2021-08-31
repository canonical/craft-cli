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

# the greeting sent, normalized across the tests so we can automatically ignore it
GREETING = "Specific greeting to be ignored"


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

    assert len(expected_lines) == len(lines)
    for expected, real in zip(expected_lines, lines):
        end_of_line = "\n" if expected.permanent else "\r"
        timestamp = TIMESTAMP_FORMAT if expected.timestamp else ""

        # the timestamp (if should be there), the text to compare, some spaces, and the CR/LN
        template = f"{timestamp}(.*?) *{end_of_line}"
        match = re.match(template, real)
        assert match, f"Line {real!r} didn't match {template!r}"
        assert match.groups()[0] == expected.text


def assert_outputs(capsys, emit, expected_out=None, expected_err=None):
    """Verify that the outputs are correct according to the expected lines."""
    # check the expected stdout and stderr outputs
    out, err = capsys.readouterr()
    if expected_out is None:
        assert not out
    else:
        compare_lines(expected_out, out)
    if expected_err is None:
        compare_lines([], err)  # this comparison will eliminate the greeting
    else:
        compare_lines(expected_err, err)

    # XXX Facundo 2021-08-26: using this so pylint does not complain; it will *really* be used
    # in next branches
    assert emit


@pytest.mark.parametrize("mode", EmitterMode)  # all modes!
def test_01_expected_cmd_result(capsys, mode):
    """Show a simple message, the expected command result."""
    emit = Emitter()
    emit.init(mode, GREETING)
    emit.message("The meaning of life is 42.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42."),
    ]
    assert_outputs(capsys, emit, expected_out=expected)


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
    emit.init(mode, GREETING)
    emit.message("The meaning of life is 42.", intermediate=True)
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42."),
    ]
    assert_outputs(capsys, emit, expected_out=expected)


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
    emit.init(mode, GREETING)
    emit.message("The meaning of life is 42.", intermediate=True)
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42.", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_out=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_greeting_when_quiet(capsys, mode):
    """Check when the greeting is sent when setting the mode to more quiet modes."""
    different_greeting = "different greeting to not be ignored"
    emit = Emitter()
    emit.init(EmitterMode.NORMAL, different_greeting)
    emit.set_mode(mode)
    emit.message("final message")
    emit.ended_ok()

    expected_out = [
        Line("final message"),
    ]
    assert_outputs(capsys, emit, expected_out=expected_out)


def test_greeting_when_verbose(capsys):
    """Check when the greeting is sent when setting the mode to VERBOSE."""
    different_greeting = "different greeting to not be ignored"
    emit = Emitter()
    emit.init(EmitterMode.NORMAL, different_greeting)
    emit.set_mode(EmitterMode.VERBOSE)
    emit.message("final message")
    emit.ended_ok()

    expected_out = [
        Line("final message"),
    ]
    expected_err = [
        Line(different_greeting, timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_out=expected_out, expected_err=expected_err)


def test_greeting_when_trace(capsys):
    """Check when the greeting is sent when setting the mode to TRACE."""
    different_greeting = "different greeting to not be ignored"
    emit = Emitter()
    emit.init(EmitterMode.NORMAL, different_greeting)
    emit.set_mode(EmitterMode.TRACE)
    emit.message("final message")
    emit.ended_ok()

    expected_out = [
        Line("final message"),
    ]
    expected_err = [
        Line(different_greeting, timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_out=expected_out, expected_err=expected_err)
