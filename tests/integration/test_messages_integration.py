#
# Copyright 2021-2023 Canonical Ltd.
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
"""

import logging
import os
import re
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Collection
from unittest.mock import patch

import pytest

from craft_cli import messages, printer, errors
from craft_cli.errors import CraftError
from craft_cli.messages import Emitter, EmitterMode

# the timestamp format (including final separator space)
TIMESTAMP_FORMAT = r"\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d.\d\d\d "

# the greeting sent and logfile, normalized across the tests so we can automatically ignore them
GREETING = "Specific greeting to be ignored"
FAKE_LOGNAME = "testapp-ignored.log"


@pytest.fixture(autouse=True)
def prepare_environment(tmp_path, monkeypatch):
    """Prepare environment to all the tests in this module."""
    # provide a fake log filepath, outside of user's appdir
    fake_logpath = tmp_path / FAKE_LOGNAME
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: fake_logpath)

    # set a very big terminal width so messages are briefly not wrapped
    monkeypatch.setattr(printer, "_get_terminal_width", lambda: 500)


@pytest.fixture(autouse=True)
def force_output_behaviour(monkeypatch, output_is_terminal):
    """Fixture to force the "terminal" or "captured" behaviours.

    Note that it's always safer to use this fixture, as the very effect of running the
    tests makes the output to be captured, so it's a good idea to be explicit.
    """
    monkeypatch.setattr(printer, "_stream_is_terminal", lambda stream: output_is_terminal)


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
    regex: bool = False  # if "text" is a regular expression instead of an exact string


def compare_lines(expected_lines: Collection[Line], raw_stream, std_stream):
    """Helper to compare expected lines to what was written to the terminal."""
    width = printer._get_terminal_width()
    terminal = printer._stream_is_terminal(std_stream)
    if expected_lines:
        assert len(raw_stream) > 0

    if terminal:
        # when showing to the terminal, it's completed always to screen width and terminated in
        # different ways, so we split lines according to that length
        assert (
            len(raw_stream) % width == 0
        ), f"Bad length {len(raw_stream)} ({width=}) {raw_stream=!r}"
        args = [iter(raw_stream)] * width
        lines = ["".join(x) for x in zip(*args)]  # pyright: ignore[reportGeneralTypeIssues]
    else:
        # when the output is captured, each line is simple and it should end in newline, so use
        # that for splitting (but don't lose the newline)
        lines = [line + "\n" for line in raw_stream.split("\n") if line]

    if lines and GREETING in lines[0]:
        lines = lines[1:]
    if lines and FAKE_LOGNAME in lines[0]:
        lines = lines[1:]

    assert len(expected_lines) == len(lines), repr(lines)
    for expected, real in zip(expected_lines, lines):  # pyright: ignore[reportGeneralTypeIssues]
        end_of_line = "\n" if expected.permanent else "\r"
        timestamp = TIMESTAMP_FORMAT if expected.timestamp else ""

        # the timestamp (if should be there), the text to compare, some spaces, and the CR/LN
        template = f"{timestamp}(.*?) *{end_of_line}"
        match = re.match(template, real)
        assert match, f"Line {real!r} didn't match {template!r}"
        if expected.regex:
            assert re.match(expected.text, match.groups()[0])
        else:
            assert match.groups()[0] == expected.text


def assert_outputs(capsys, emit, expected_out=None, expected_err=None, expected_log=None):
    """Verify that the outputs are correct according to the expected lines."""
    # check the expected stdout and stderr outputs
    out, err = capsys.readouterr()
    if expected_out is None:
        assert not out
    else:
        compare_lines(expected_out, out, sys.stdout)
    if expected_err is None:
        compare_lines(
            [], err, sys.stderr
        )  # this comparison will eliminate the greeting and log path lines
    else:
        compare_lines(expected_err, err, sys.stderr)

    # get the logged text, always validating a valid timestamp format at the beginning
    # of each line
    with open(emit._log_filepath, "rt", encoding="utf8") as filehandler:
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


@pytest.mark.parametrize("output_is_terminal", [None])
def test_exposed_api():
    """Verify names are properly exposed."""
    from craft_cli import emit

    assert isinstance(emit, messages.Emitter)

    from craft_cli import EmitterMode as test_em

    assert test_em is EmitterMode

    from craft_cli import CraftError as test_cs

    assert test_cs is CraftError


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_message_expected_cmd_result_quiet(capsys):
    """Do not show the message, but log it."""
    emit = Emitter()
    emit.init(EmitterMode.QUIET, "testapp", GREETING)
    emit.message("The meaning of life is 42.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42."),
    ]
    assert_outputs(capsys, emit, expected_out=None, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.BRIEF,
        EmitterMode.VERBOSE,
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_message_expected_cmd_result_not_quiet(capsys, mode):
    """Show a simple message, the expected command result."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    emit.message("The meaning of life is 42.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42."),
    ]
    assert_outputs(capsys, emit, expected_out=expected, expected_log=expected)


@pytest.mark.parametrize("permanent", [True, False])
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_progress_quiet(capsys, permanent):
    """Show a progress message being in quiet mode."""
    emit = Emitter()
    emit.init(EmitterMode.QUIET, "testapp", GREETING)
    emit.progress("The meaning of life is 42.", permanent=permanent)
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42.", permanent=False),
    ]
    assert_outputs(capsys, emit, expected_log=expected)


@pytest.mark.parametrize("output_is_terminal", [True])
def test_progress_brief_terminal(capsys):
    """Show a progress message in brief mode."""
    emit = Emitter()
    emit.init(EmitterMode.BRIEF, "testapp", GREETING)
    emit.progress("The meaning of life is 42.")
    emit.progress("Another message.")
    emit.ended_ok()

    expected_term = [
        Line("The meaning of life is 42.", permanent=False),
        Line("Another message.", permanent=False),
        # This cleaner line is inserted by the printer stop
        # sequence to reset the last ephemeral print to terminal.
        Line("", permanent=False),
    ]
    expected_log = [
        Line("The meaning of life is 42.", permanent=False),
        Line("Another message.", permanent=False),
    ]
    assert_outputs(capsys, emit, expected_err=expected_term, expected_log=expected_log)


@pytest.mark.parametrize("output_is_terminal", [False])
def test_progress_brief_captured(capsys, monkeypatch):
    """Show a progress message in brief mode but when the output is captured."""
    emit = Emitter()
    emit.init(EmitterMode.BRIEF, "testapp", GREETING)
    emit.progress("The meaning of life is 42.")
    emit.progress("Another message.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42.", permanent=True),
        Line("Another message.", permanent=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_progress_brief_permanent(capsys, monkeypatch):
    """Show a progress message with permanent flag in brief mode."""
    emit = Emitter()
    emit.init(EmitterMode.BRIEF, "testapp", GREETING)
    emit.progress("The meaning of life is 42.", permanent=True)
    emit.progress("Another message.", permanent=True)
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42.", permanent=True),
        Line("Another message.", permanent=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize("permanent", [True, False])
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_progress_verbose(capsys, permanent):
    """Show a progress message in verbose and debug modes."""
    emit = Emitter()
    emit.init(EmitterMode.VERBOSE, "testapp", GREETING)
    emit.progress("The meaning of life is 42.", permanent=permanent)
    emit.progress("Another message.", permanent=permanent)
    emit.ended_ok()

    # ephemeral ends up being ignored, as in verbose and debug no lines are overridden
    expected = [
        Line("The meaning of life is 42.", permanent=True),
        Line("Another message.", permanent=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
@pytest.mark.parametrize("permanent", [True, False])
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_progress_developer_modes(capsys, mode, permanent):
    """Show a progress message in developer modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    emit.progress("The meaning of life is 42.", permanent=permanent)
    emit.progress("Another message.", permanent=permanent)
    emit.ended_ok()

    # ephemeral ends up being ignored, as in verbose and debug no lines are overridden
    expected = [
        Line("The meaning of life is 42.", permanent=True, timestamp=True),
        Line("Another message.", permanent=True, timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_progressbar_quiet(capsys):
    """Show a progress bar when quiet mode."""
    emit = Emitter()
    emit.init(EmitterMode.QUIET, "testapp", GREETING)
    with emit.progress_bar("Uploading stuff", 1788) as progress:
        for uploaded in [700, 700, 388]:
            progress.advance(uploaded)
    emit.ended_ok()

    # nothing to the screen, just to the log
    expected_log = [
        Line("Uploading stuff (--->)"),
        Line("Uploading stuff (<---)"),
    ]
    assert_outputs(capsys, emit, expected_log=expected_log)


@pytest.mark.parametrize("output_is_terminal", [True])
def test_progressbar_brief_terminal(capsys, monkeypatch):
    """Show a progress bar in brief mode."""
    # fake size so lines to compare are static
    monkeypatch.setattr(printer, "_get_terminal_width", lambda: 60)

    emit = Emitter()

    # patch `set_mode` so it's not really run and set the mode manually, as we do NOT want
    # the "Logging execution..." message to be sent to screen because it's too long and will
    # break the tests. Note we want the fake terminal width to be small so we can "draw" here
    # in the test the progress bar we want to see.
    emit.set_mode = lambda mode: None
    emit.init(EmitterMode.BRIEF, "testapp", GREETING)
    emit._mode = EmitterMode.BRIEF

    with emit.progress_bar("Uploading stuff", 1788) as progress:
        for uploaded in [700, 700, 388]:
            progress.advance(uploaded)
    emit.progress("And so on")  # just a line so last progress line is not artificially permanent
    emit.ended_ok()

    expected_screen = [
        Line("Uploading stuff (--->)", permanent=False),
        Line("Uploading stuff [████████████                    ] 700/1788", permanent=False),
        Line("Uploading stuff [████████████████████████       ] 1400/1788", permanent=False),
        Line("Uploading stuff [███████████████████████████████] 1788/1788", permanent=False),
        Line("Uploading stuff (<---)", permanent=False),
        Line("And so on", permanent=False),
        # This cleaner line is inserted by the printer stop
        # sequence to reset the last ephemeral print to terminal.
        Line("", permanent=False),
    ]
    expected_log = [
        Line("Uploading stuff (--->)"),
        Line("Uploading stuff (<---)"),
        Line("And so on"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_screen, expected_log=expected_log)


@pytest.mark.parametrize("output_is_terminal", [True])
def test_progressbar_brief_permanent_terminal(capsys, monkeypatch):
    """Show a progress bar in brief mode."""
    # fake size so lines to compare are static
    monkeypatch.setattr(printer, "_get_terminal_width", lambda: 60)

    emit = Emitter()

    # patch `set_mode` so it's not really run and set the mode manually, as we do NOT want
    # the "Logging execution..." message to be sent to screen because it's too long and will
    # break the tests. Note we want the fake terminal width to be small so we can "draw" here
    # in the test the progress bar we want to see.
    emit.set_mode = lambda mode: None
    emit.init(EmitterMode.BRIEF, "testapp", GREETING)
    emit._mode = EmitterMode.BRIEF

    with emit.progress_bar("Uploading stuff", 1788) as progress:
        for uploaded in [700, 700, 388]:
            progress.advance(uploaded)
    emit.progress(
        "And so on", permanent=True
    )  # just a line so last progress line is not artificially permanent
    emit.ended_ok()

    expected_screen = [
        Line("Uploading stuff (--->)", permanent=False),
        Line("Uploading stuff [████████████                    ] 700/1788", permanent=False),
        Line("Uploading stuff [████████████████████████       ] 1400/1788", permanent=False),
        Line("Uploading stuff [███████████████████████████████] 1788/1788", permanent=False),
        Line("Uploading stuff (<---)", permanent=False),
        Line("And so on", permanent=True),
    ]
    expected_log = [
        Line("Uploading stuff (--->)"),
        Line("Uploading stuff (<---)"),
        Line("And so on"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_screen, expected_log=expected_log)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.BRIEF,
        EmitterMode.VERBOSE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [False])
def test_progressbar_captured_quietish(capsys, monkeypatch, mode):
    """When captured, never output the progress itself, just the first line."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)

    with emit.progress_bar("Uploading stuff", 1788) as progress:
        for uploaded in [700, 700, 388]:
            progress.advance(uploaded)
    emit.ended_ok()

    expected = [
        Line("Uploading stuff (--->)", permanent=True),
        Line("Uploading stuff (<---)", permanent=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [False])
def test_progressbar_captured_developer_modes(capsys, monkeypatch, mode):
    """When captured, never output the progress itself, just the first line."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)

    with emit.progress_bar("Uploading stuff", 1788) as progress:
        for uploaded in [700, 700, 388]:
            progress.advance(uploaded)
    emit.ended_ok()

    expected = [
        Line("Uploading stuff (--->)", permanent=True, timestamp=True),
        Line("Uploading stuff (<---)", permanent=True, timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize("output_is_terminal", [True])
def test_progressbar_verbose(capsys, monkeypatch):
    """Show a progress bar in verbose mode."""
    # fake size so lines to compare are static
    monkeypatch.setattr(printer, "_get_terminal_width", lambda: 60)

    emit = Emitter()

    # patch `set_mode` so it's not really run and set the mode manually, as we do NOT want
    # the "Logging execution..." message to be sent to screen because it's too long and will
    # break the tests. Note we want the fake terminal width to be small so we can "draw" here
    # in the test the progress bar we want to see.
    emit.set_mode = lambda mode: None
    emit.init(EmitterMode.VERBOSE, "testapp", GREETING)
    emit._mode = EmitterMode.VERBOSE

    with emit.progress_bar("Uploading stuff", 1788) as progress:
        for uploaded in [700, 700, 388]:
            progress.advance(uploaded)
    emit.progress("And so on")  # just a line so last progress line is not artificially permanent
    emit.ended_ok()

    expected_screen = [
        Line("Uploading stuff (--->)", permanent=True),  # this starting line will endure
        Line("Uploading stuff [████████████                    ] 700/1788", permanent=False),
        Line("Uploading stuff [████████████████████████       ] 1400/1788", permanent=False),
        Line("Uploading stuff [███████████████████████████████] 1788/1788", permanent=False),
        Line("Uploading stuff (<---)", permanent=True),  # this closing line will endure
        Line("And so on", permanent=True),
    ]
    expected_log = [
        Line("Uploading stuff (--->)"),
        Line("Uploading stuff (<---)"),
        Line("And so on"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_screen, expected_log=expected_log)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True])
def test_progressbar_developer_modes(capsys, mode, monkeypatch):
    """Show a progress bar in debug and trace modes."""
    # fake size so lines to compare are static
    monkeypatch.setattr(printer, "_get_terminal_width", lambda: 60)

    emit = Emitter()

    # patch `set_mode` so it's not really run and set the mode manually, as we do NOT want
    # the "Logging execution..." message to be sent to screen because it's too long and will
    # break the tests. Note we want the fake terminal width to be small so we can "draw" here
    # in the test the progress bar we want to see.
    emit.set_mode = lambda mode: None
    emit.init(mode, "testapp", GREETING)
    emit._mode = mode

    with emit.progress_bar("Uploading stuff", 1788) as progress:
        for uploaded in [700, 700, 388]:
            progress.advance(uploaded)
    emit.progress("And so on")  # just a line so last progress line is not artificially permanent
    emit.ended_ok()

    expected_screen = [
        Line("Uploading stuff (--->)", permanent=True, timestamp=True),  # this line will endure
        Line("Uploading stuff [███     ] 700/1788", permanent=False, timestamp=True),
        Line("Uploading stuff [█████  ] 1400/1788", permanent=False, timestamp=True),
        Line("Uploading stuff [███████] 1788/1788", permanent=False, timestamp=True),
        Line("Uploading stuff (<---)", permanent=True, timestamp=True),  # this line will endure
        Line("And so on", permanent=True, timestamp=True),
    ]
    expected_log = [
        Line("Uploading stuff (--->)"),
        Line("Uploading stuff (<---)"),
        Line("And so on"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_screen, expected_log=expected_log)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.BRIEF,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_verbose_in_quietish_modes(capsys, mode):
    """The verbose method in more quietish modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    emit.verbose("The meaning of life is 42.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42."),
    ]
    assert_outputs(capsys, emit, expected_log=expected)


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_verbose_in_verbose_mode(capsys):
    """The verbose method in the verbose mode."""
    emit = Emitter()
    emit.init(EmitterMode.VERBOSE, "testapp", GREETING)
    emit.verbose("The meaning of life is 42.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42.", timestamp=False),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_verbose_in_developer_modes(capsys, mode):
    """The verbose method in developer modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    emit.verbose("The meaning of life is 42.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42.", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.BRIEF,
        EmitterMode.VERBOSE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_debug_in_quietish_modes(capsys, mode):
    """The debug method in more quietish modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    emit.debug("The meaning of life is 42.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42."),
    ]
    assert_outputs(capsys, emit, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_debug_in_developer_modes(capsys, mode):
    """The debug method in developer modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    emit.debug("The meaning of life is 42.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42.", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.BRIEF,
        EmitterMode.VERBOSE,
        EmitterMode.DEBUG,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_trace_in_quietish_modes(capsys, mode):
    """The trace method in more quietish modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    emit.trace("The meaning of life is 42.")
    emit.ended_ok()
    assert_outputs(capsys, emit)  # nothing, not even in the logs!!


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_trace_in_trace_mode(capsys):
    """The trace method in trace mode."""
    emit = Emitter()
    emit.init(EmitterMode.TRACE, "testapp", GREETING)
    emit.trace("The meaning of life is 42.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42.", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_third_party_output_quiet(capsys, tmp_path):
    """Manage the streams produced for sub-executions, more quiet modes."""
    # something to execute
    script = tmp_path / "script.py"
    script.write_text(
        textwrap.dedent(
            """
        import sys
        print("foobar out", flush=True)
        print("foobar err", file=sys.stderr, flush=True)
    """
        )
    )
    emit = Emitter()
    emit.init(EmitterMode.QUIET, "testapp", GREETING)
    with emit.open_stream("Testing stream") as stream:
        subprocess.run([sys.executable, script], stdout=stream, stderr=stream, check=True)
    emit.ended_ok()

    expected = [
        Line("Testing stream"),
        Line(":: foobar out"),
        Line(":: foobar err"),
    ]
    assert_outputs(capsys, emit, expected_log=expected)


@pytest.mark.parametrize("output_is_terminal", [True])
def test_third_party_output_brief_terminal(capsys, tmp_path):
    """Manage the streams produced for sub-executions, brief mode, to the terminal."""
    # something to execute
    script = tmp_path / "script.py"
    script.write_text(
        textwrap.dedent(
            """
        import sys
        print("foobar out", flush=True)
        print("foobar err", file=sys.stderr, flush=True)
    """
        )
    )
    emit = Emitter()
    emit.init(EmitterMode.BRIEF, "testapp", GREETING)
    with emit.open_stream("Testing stream") as stream:
        subprocess.run([sys.executable, script], stdout=stream, stderr=stream, check=True)
    emit.ended_ok()

    expected_err = [
        Line("Testing stream", permanent=False),
        Line(":: foobar out", permanent=False),
        Line(":: foobar err", permanent=False),
        # This cleaner line is inserted by the printer stop
        # sequence to reset the last ephemeral print to terminal.
        Line("", permanent=False),
    ]
    expected_log = [
        Line("Testing stream"),
        Line(":: foobar out"),
        Line(":: foobar err"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_err, expected_log=expected_log)


@pytest.mark.parametrize("output_is_terminal", [False])
def test_third_party_output_brief_captured(capsys, tmp_path):
    """Manage the streams produced for sub-executions, brief mode, captured."""
    # something to execute
    script = tmp_path / "script.py"
    script.write_text(
        textwrap.dedent(
            """
        import sys
        print("foobar out", flush=True)
        print("foobar err", file=sys.stderr, flush=True)
    """
        )
    )
    emit = Emitter()
    emit.init(EmitterMode.BRIEF, "testapp", GREETING)
    with emit.open_stream("Testing stream") as stream:
        subprocess.run([sys.executable, script], stdout=stream, stderr=stream, check=True)
    emit.ended_ok()

    expected = [
        Line("Testing stream"),
        Line(":: foobar out"),
        Line(":: foobar err"),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_third_party_output_verbose(capsys, tmp_path):
    """Manage the streams produced for sub-executions, verbose mode."""
    # something to execute
    script = tmp_path / "script.py"
    script.write_text(
        textwrap.dedent(
            """
        import sys
        print("foobar out", flush=True)
        print("foobar err", file=sys.stderr, flush=True)
    """
        )
    )
    emit = Emitter()
    emit.init(EmitterMode.VERBOSE, "testapp", GREETING)
    with emit.open_stream("Testing stream") as stream:
        subprocess.run([sys.executable, script], stdout=stream, stderr=stream, check=True)
    emit.ended_ok()

    expected = [
        Line("Testing stream"),
        Line(":: foobar out"),
        Line(":: foobar err"),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_third_party_output_developer_modes(capsys, tmp_path, mode):
    """Manage the streams produced for sub-executions, developer modes."""
    # something to execute
    script = tmp_path / "script.py"
    script.write_text(
        textwrap.dedent(
            """
        import sys
        print("foobar out", flush=True)
        print("foobar err", file=sys.stderr, flush=True)
    """
        )
    )
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    with emit.open_stream("Testing stream") as stream:
        subprocess.run([sys.executable, script], stdout=stream, stderr=stream, check=True)
    emit.ended_ok()

    expected = [
        Line("Testing stream", timestamp=True),
        Line(":: foobar out", timestamp=True),
        Line(":: foobar err", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.BRIEF,
        EmitterMode.VERBOSE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_simple_errors_quietly(capsys, mode):
    """Error because of application or external rules, final user modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    error = CraftError(
        "Cannot find config file 'somepath'.",
    )
    emit.error(error)

    expected = [
        Line("Cannot find config file 'somepath'."),
        Line(f"Full execution log: {str(emit._log_filepath)!r}"),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_simple_errors_debugish(capsys, mode):
    """Error because of application or external rules, more debugish modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    error = CraftError(
        "Cannot find config file 'somepath'.",
    )
    emit.error(error)

    expected = [
        Line("Cannot find config file 'somepath'.", timestamp=True),
        Line(f"Full execution log: {str(emit._log_filepath)!r}", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.BRIEF,
        EmitterMode.VERBOSE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_error_api_quietly(capsys, mode):
    """Somewhat expected API error, final user modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    full_error = {"message": "Invalid channel.", "code": "BAD-CHANNEL"}
    error = CraftError("Invalid channel.", details=str(full_error))
    emit.error(error)

    expected_err = [
        Line("Invalid channel."),
        Line(f"Full execution log: {str(emit._log_filepath)!r}"),
    ]
    expected_log = [
        Line("Invalid channel."),
        Line(f"Detailed information: {full_error}"),
        Line(f"Full execution log: {str(emit._log_filepath)!r}"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_err, expected_log=expected_log)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_error_api_debugish(capsys, mode):
    """Somewhat expected API error, more debugish modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    full_error = {"message": "Invalid channel.", "code": "BAD-CHANNEL"}
    error = CraftError("Invalid channel.", details=str(full_error))
    emit.error(error)

    expected = [
        Line("Invalid channel.", timestamp=True),
        Line(f"Detailed information: {full_error}", timestamp=True),
        Line(f"Full execution log: {str(emit._log_filepath)!r}", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.BRIEF,
        EmitterMode.VERBOSE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_error_unexpected_quietly(capsys, mode):
    """Unexpected error from a 3rd party or application crash, final user modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    try:
        raise ValueError("pumba")
    except ValueError as exc:
        error = CraftError("First message.")
        error.__cause__ = exc
        with patch("craft_cli.messages._get_traceback_lines", return_value=["foo", "bar"]):
            emit.error(error)

    expected_err = [
        Line("First message."),
        Line(f"Full execution log: {str(emit._log_filepath)!r}"),
    ]
    expected_log = [
        Line("First message."),
        Line("foo"),
        Line("bar"),
        Line(f"Full execution log: {str(emit._log_filepath)!r}"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_err, expected_log=expected_log)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_error_unexpected_debugish(capsys, mode):
    """Unexpected error from a 3rd party or application crash, more debugish modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    try:
        raise ValueError("pumba")
    except ValueError as exc:
        error = CraftError("First message.")
        error.__cause__ = exc
        with patch("craft_cli.messages._get_traceback_lines", return_value=["foo", "bar"]):
            emit.error(error)

    expected = [
        Line("First message.", timestamp=True),
        Line("foo", timestamp=True),
        Line("bar", timestamp=True),
        Line(f"Full execution log: {str(emit._log_filepath)!r}", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.BRIEF,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_logging_in_quietish_modes(capsys, logger, mode):
    """Handle the different logging levels when in quiet and brief modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    logger.error("--error-- %s", "with args")
    logger.warning("--warning--")
    logger.info("--info--")
    logger.debug("--debug--")
    logger.log(5, "--custom low level--")
    emit.ended_ok()

    expected = [
        Line("--error-- with args"),
        Line("--warning--"),
        Line("--info--"),
        Line("--debug--"),
    ]
    assert_outputs(capsys, emit, expected_log=expected)


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_logging_in_verbose_mode(capsys, logger):
    """Handle the different logging levels when in verbose mode."""
    emit = Emitter()
    emit.init(EmitterMode.VERBOSE, "testapp", GREETING)
    logger.error("--error-- %s", "with args")
    logger.warning("--warning--")
    logger.info("--info--")
    logger.debug("--debug--")
    logger.log(5, "--custom low level--")
    emit.ended_ok()

    expected_err = [
        Line("--error-- with args"),
        Line("--warning--"),
        Line("--info--"),
    ]
    expected_log = expected_err + [
        Line("--debug--"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_err, expected_log=expected_log)


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_logging_in_debug_mode(capsys, logger):
    """Handle the different logging levels when in debug mode."""
    emit = Emitter()
    emit.init(EmitterMode.DEBUG, "testapp", GREETING)
    logger.error("--error-- %s", "with args")
    logger.warning("--warning--")
    logger.info("--info--")
    logger.debug("--debug--")
    logger.log(5, "--custom low level--")
    emit.ended_ok()

    expected = [
        Line("--error-- with args", timestamp=True),
        Line("--warning--", timestamp=True),
        Line("--info--", timestamp=True),
        Line("--debug--", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_logging_in_trace_mode(capsys, logger):
    """Handle the different logging levels when in trace mode."""
    emit = Emitter()
    emit.init(EmitterMode.TRACE, "testapp", GREETING)
    logger.error("--error-- %s", "with args")
    logger.warning("--warning--")
    logger.info("--info--")
    logger.debug("--debug--")
    logger.log(5, "--custom low level--")
    emit.ended_ok()

    expected = [
        Line("--error-- with args", timestamp=True),
        Line("--warning--", timestamp=True),
        Line("--info--", timestamp=True),
        Line("--debug--", timestamp=True),
        Line("--custom low level--", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_initial_messages_quiet_mode(capsys, monkeypatch, tmp_path):
    """Check the initial messages are sent when setting the mode to QUIET."""
    # use different greeting and file logpath so we can actually test them
    different_greeting = "different greeting to not be ignored"
    different_logpath = tmp_path / "otherfile.log"
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: different_logpath)

    emit = Emitter()
    emit.init(EmitterMode.BRIEF, "testapp", different_greeting)
    emit.message("initial message")
    emit.set_mode(EmitterMode.QUIET)
    emit.message("second message")
    emit.ended_ok()

    expected_out = [
        Line("initial message"),
    ]
    expected_log = [
        Line(different_greeting),
        Line("initial message"),
        Line("second message"),
    ]
    assert_outputs(capsys, emit, expected_out=expected_out, expected_log=expected_log)


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_initial_messages_brief_mode(capsys, monkeypatch, tmp_path):
    """Check the initial messages are sent when setting the mode to BRIEF."""
    # use different greeting and file logpath so we can actually test them
    different_greeting = "different greeting to not be ignored"
    different_logpath = tmp_path / "otherfile.log"
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: different_logpath)

    emit = Emitter()
    emit.init(EmitterMode.QUIET, "testapp", different_greeting)
    emit.message("initial message")
    emit.set_mode(EmitterMode.BRIEF)
    emit.message("second message")
    emit.ended_ok()

    expected_out = [
        Line("second message"),
    ]
    expected_log = [
        Line(different_greeting),
        Line("initial message"),
        Line("second message"),
    ]
    assert_outputs(capsys, emit, expected_out=expected_out, expected_log=expected_log)


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_initial_messages_verbose(capsys, tmp_path, monkeypatch):
    """Check the initial messages are sent when setting the mode to VERBOSE."""
    # use different greeting and file logpath so we can actually test them
    different_greeting = "different greeting to not be ignored"
    different_logpath = tmp_path / "otherfile.log"
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: different_logpath)

    emit = Emitter()
    emit.init(EmitterMode.QUIET, "testapp", different_greeting)
    emit.progress("initial message")
    emit.set_mode(EmitterMode.VERBOSE)
    emit.progress("second message")
    emit.ended_ok()

    expected_err = [
        Line(different_greeting),
        Line(f"Logging execution to {str(different_logpath)!r}"),
        Line("second message"),
    ]
    expected_log = [
        Line(different_greeting),
        Line("initial message"),
        Line("second message"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_err, expected_log=expected_log)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_initial_messages_developer_modes(capsys, tmp_path, monkeypatch, mode):
    """Check the initial messages are sent when setting developer modes."""
    # use different greeting and file logpath so we can actually test them
    different_greeting = "different greeting to not be ignored"
    different_logpath = tmp_path / "otherfile.log"
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: different_logpath)

    emit = Emitter()
    emit.init(EmitterMode.QUIET, "testapp", different_greeting)
    emit.progress("initial message")
    emit.set_mode(mode)
    emit.progress("second message")
    emit.ended_ok()

    expected_err = [
        Line(different_greeting, timestamp=True),
        Line(f"Logging execution to {str(different_logpath)!r}", timestamp=True),
        Line("second message", timestamp=True),
    ]
    expected_log = [
        Line(different_greeting),
        Line("initial message"),
        Line("second message"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_err, expected_log=expected_log)


@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_logging_after_closing(capsys, logger):
    """We don't control when log messages are generated, be safe with after-stop ones."""
    emit = Emitter()
    emit.init(EmitterMode.VERBOSE, "testapp", GREETING)
    logger.info("info 1")
    emit.ended_ok()
    logger.info("info 2")

    expected = [
        Line("info 1"),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


def _parse_timestamp(text):
    """Parse a timestamp from its text format to seconds from epoch."""
    date_and_time, msec = text.strip().split(".")
    dt_ = datetime.strptime(date_and_time, "%Y-%m-%d %H:%M:%S")
    tstamp = dt_.timestamp()
    assert len(msec) == 3
    tstamp += int(msec) / 1000
    return tstamp


@pytest.mark.parametrize(
    "loops, sleep, max_repetitions",
    [
        (100, 0.01, 30),
        (1000, 0.001, 100),
        (10, 0.1, 2),
    ],
)
@pytest.mark.parametrize("output_is_terminal", [True, False])
def test_capture_delays(tmp_path, loops, sleep, max_repetitions):
    """Check that there are no noticeable delays when capturing output.

    Note that the sub Python process is run in unbuffered mode. If the `-u` is removed from
    the command line, it will not output information as soon it's available, and the test
    will fail. This somewhat proves that as long the subprocess is quick to output text,
    the capturing part is fine.
    """
    # something to execute
    script = tmp_path / "script.py"

    script.write_text(
        textwrap.dedent(
            f"""
        import random
        import time
        from datetime import datetime

        for _ in range({loops}):
            tstamp = datetime.now().isoformat(sep=" ", timespec="milliseconds")
            print(tstamp, "short text to repeat " * random.randint(1, {max_repetitions}))
            time.sleep({sleep})
        """
        )
    )
    emit = Emitter()
    emit.init(EmitterMode.QUIET, "testapp", GREETING)
    with emit.open_stream("Testing stream") as stream:
        cmd = [sys.executable, "-u", script]
        subprocess.run(cmd, stdout=stream, check=True)
    emit.ended_ok()

    timestamps = []
    with open(emit._log_filepath, "rt", encoding="utf8") as filehandler:  # type: ignore
        for line in filehandler:
            match = re.match(rf"({TIMESTAMP_FORMAT}):: ({TIMESTAMP_FORMAT}).*\n", line)
            if not match:
                continue
            timestamps.append([_parse_timestamp(x) for x in match.groups()])

    if not timestamps:
        pytest.fail("Bad logs, couldn't retrieve timestamps")

    # no big deltas in most of the messages! in a development machine the
    # delay limit can be 2 ms and still passes ok, raising it because CIs
    # are slower (a limit that is still useful: when subprocess Python
    # is run without the `-u` option average delays are around 500 ms.
    delays = [t_outside - t_inside for t_outside, t_inside in timestamps]
    too_big = [delay for delay in delays if delay > 0.050]
    if len(too_big) > loops / 20:
        pytest.fail(f"Delayed capture: {too_big} avg delay is {sum(delays) / len(delays):.3f}")


@pytest.mark.parametrize("output_is_terminal", [True])
def test_progress_and_message(capsys, logger):
    emit = Emitter()
    emit.init(EmitterMode.BRIEF, "testapp", GREETING)
    emit.progress("The meaning of life is 42.")
    emit.progress("Another message.")
    emit.message("Finished successfully.")
    emit.ended_ok()

    expected_term = [
        Line("The meaning of life is 42.", permanent=False),
        Line("Another message.", permanent=False),
    ]
    expected_out = [Line("Finished successfully.", permanent=True)]
    expected_log = [
        Line("The meaning of life is 42.", permanent=False),
        Line("Another message.", permanent=False),
        Line("Finished successfully.", permanent=False),
    ]
    assert_outputs(
        capsys,
        emit,
        expected_err=expected_term,
        expected_out=expected_out,
        expected_log=expected_log,
    )


@pytest.mark.parametrize("output_is_terminal", [True])
def test_streaming_brief(capsys, logger):
    """Test the overall behavior of the "streaming_brief" feature regarding the terminal
    and the generated logs."""

    emit = Emitter()
    emit.init(EmitterMode.BRIEF, "testapp", GREETING, streaming_brief=True)

    emit.progress("First stage", permanent=False)
    logger.info("info 1")
    logger.debug("debug 1")
    logger.info("info 2")
    logger.debug("debug 2")
    emit.progress("Done first stage", permanent=True)

    emit.progress("Second stage", permanent=False)
    logger.info("info 1")
    logger.debug("debug 1")
    logger.info("info 2")
    logger.debug("debug 2")
    emit.progress("Done second stage", permanent=True)

    emit.ended_ok()

    # Messages shown on the terminal: progress messages, plus INFO-level log messages
    # "streamed" into the most recent non-permanent progress() message.
    expected_err = [
        Line("First stage", permanent=False),
        Line("First stage :: info 1", permanent=False),
        Line("First stage :: info 2", permanent=False),
        Line("Done first stage", permanent=True),
        Line("Second stage", permanent=False),
        Line("Second stage :: info 1", permanent=False),
        Line("Second stage :: info 2", permanent=False),
        Line("Done second stage", permanent=True),
    ]

    # Messages saved to the logfile: progress messages, plus all log messages. Note that
    # INFO-level log messages are _not_ "prefixed" with the progress messages' text.
    expected_log = [
        Line("First stage"),
        Line("info 1"),
        Line("debug 1"),
        Line("info 2"),
        Line("debug 2"),
        Line("Done first stage"),
        Line("Second stage"),
        Line("info 1"),
        Line("debug 1"),
        Line("info 2"),
        Line("debug 2"),
        Line("Done second stage"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_err, expected_log=expected_log)


@pytest.mark.parametrize("output_is_terminal", [True])
def test_streaming_brief_open_stream(capsys, logger):
    """Test the interaction between the "streaming brief" mode and the open_stream()."""

    emit = Emitter()
    emit.init(EmitterMode.BRIEF, "testapp", GREETING, streaming_brief=True)

    emit.progress("Begin stage", permanent=False)
    with emit.open_stream("Opening stream") as write_pipe:
        os.write(write_pipe, b"Message inside stream\n")
    emit.progress("Done stage", permanent=True)
    emit.ended_ok()

    # Messages written to the open_stream()'s pipe get prefixed when writing to the
    # terminal...
    expected_err = [
        Line("Begin stage", permanent=False),
        Line("Begin stage :: Opening stream", permanent=False),
        Line("Begin stage :: Message inside stream", permanent=False),
        Line("Done stage", permanent=True),
    ]
    # ... but not when writing to the logfile.
    expected_log = [
        Line("Begin stage"),
        Line("Opening stream"),
        Line(":: Message inside stream"),
        Line("Done stage"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_err, expected_log=expected_log)


@pytest.mark.parametrize("output_is_terminal", [True])
def test_streaming_brief_messages(capsys, logger, monkeypatch):
    """Test that emit.message() clears the "streaming_brief" prefix."""
    emit = Emitter()
    emit.init(EmitterMode.BRIEF, "testapp", GREETING, streaming_brief=True)

    emit.progress("Doing process.", permanent=False)
    emit.message("Process finished successfully.")

    emit.ended_ok()

    expected_err = [
        Line("Doing process.", permanent=False),
    ]
    expected_out = [
        Line("Process finished successfully.", permanent=True),
    ]

    expected_log = [
        Line("Doing process."),
        Line("Process finished successfully."),
    ]
    assert_outputs(
        capsys,
        emit,
        expected_err=expected_err,
        expected_out=expected_out,
        expected_log=expected_log,
    )


@pytest.mark.parametrize("output_is_terminal", [True])
def test_streaming_brief_error(capsys, logger, monkeypatch):
    """Test that emit.error() clears the "streaming_brief" prefix."""
    emit = Emitter()
    emit.init(EmitterMode.BRIEF, "testapp", GREETING, streaming_brief=True)

    emit.progress("Doing process.", permanent=False)

    error = errors.CraftError(message="An error happened!", resolution="Detailed resolution.")
    emit.error(error)

    expected_err = [
        Line("Doing process.", permanent=False),
        Line("An error happened!", permanent=True),
        Line("Recommended resolution: Detailed resolution.", permanent=True),
        Line(f"Full execution log: {str(emit._log_filepath)!r}"),
    ]
    expected_log = expected_err
    assert_outputs(
        capsys,
        emit,
        expected_err=expected_err,
        expected_log=expected_log,
    )


@pytest.fixture
def init_emitter():
    """Empty fixture to disable the "global", autouse init_emitter."""


@pytest.mark.parametrize("output_is_terminal", [True])
def test_streaming_brief_spinner(capsys, logger, monkeypatch, init_emitter):
    """Test the interaction between the "streaming brief" mode and the spinner."""

    # Set the spinner delays to fairly long values to try to get some determinism
    # with this test.
    monkeypatch.setattr(printer, "_SPINNER_THRESHOLD", 0.8)
    monkeypatch.setattr(printer, "_SPINNER_DELAY", 10)
    monkeypatch.setattr(printer, "TESTMODE", False)

    emit = Emitter()
    emit.init(EmitterMode.BRIEF, "testapp", GREETING, streaming_brief=True)

    emit.progress("Begin stage", permanent=False)
    time.sleep(1)
    with emit.open_stream("Opening stream") as write_pipe:
        os.write(write_pipe, b"Info message\n")
    time.sleep(1)
    emit.progress("Done stage", permanent=True)
    emit.ended_ok()

    # The spinner-added messages should contain both the prefix and the "submessage".
    expected_err = [
        Line("Begin stage", permanent=False),
        Line(r"Begin stage - \(0.[7-9]s\)", permanent=False, regex=True),
        Line("Begin stage", permanent=False),
        Line("Begin stage :: Opening stream", permanent=False),
        Line("Begin stage :: Info message", permanent=False),
        Line(r"Begin stage :: Info message - \(0.[7-9]s\)", permanent=False, regex=True),
        Line("Begin stage :: Info message", permanent=False),
        Line("Done stage", permanent=True),
    ]
    expected_log = [
        Line("Begin stage"),
        Line("Opening stream"),
        Line(":: Info message"),
        Line("Done stage"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_err, expected_log=expected_log)


@pytest.mark.parametrize("output_is_terminal", [True])
def test_secrets_integrated(capsys, logger, monkeypatch, init_emitter):
    """Test the output of secrets through various input methods"""
    monkeypatch.setattr(printer, "_get_terminal_width", lambda: 60)

    emit = Emitter()
    emit.init(EmitterMode.BRIEF, "testapp", GREETING, streaming_brief=True)

    emit.set_secrets(["banana", "watermelon"])

    # Regular message written through the emitter
    emit.message("Apple banana orange watermelon version 1.0")

    # A progress message
    emit.progress("Begin stage: banana", permanent=False)
    # A message stream, and its pipe
    with emit.open_stream("Opening stream: watermelon") as write_pipe:
        os.write(write_pipe, b"Info message: watermelon\n")
    emit.progress("Done stage: banana", permanent=True)

    # Log messages
    logger.debug("Log message: apple")
    logger.info("Log message: banana")
    logger.warning("Log message: orange")
    logger.error("Log message: watermelon")

    # Print a string via regular "print". Two notes:
    # 1) This string will NOT be secrets-masked because it completely bypasses the printer
    # 2) We pad the string to 60 characters when printing to satisfy assert_outputs().
    raw_string = "Raw print: apple banana orange watermelon"
    print(raw_string + " " * (60 - len(raw_string) - 1))

    with emit.pause():
        # Emitter is paused: logged messages aren't printed/git logged (masked or otherwise).
        logger.info("Paused emitter log message: apple banana")

    emit.ended_ok()

    expected_out = [
        Line("Apple ***** orange ***** version 1.0", permanent=True),
        Line("Raw print: apple banana orange watermelon", permanent=True),
    ]

    expected_err = [
        Line("Begin stage: *****", permanent=False),
        Line("Begin stage: ***** :: Opening stream: *****", permanent=False),
        Line("Begin stage: ***** :: Info message: *****", permanent=False),
        Line("Done stage: *****", permanent=True),
        Line("Log message: *****", permanent=False),
        Line("Log message: orange", permanent=False),
        Line("Log message: *****", permanent=False),
        Line("", permanent=False),
    ]
    expected_log = [
        Line("Apple ***** orange ***** version 1.0"),
        Line("Begin stage: *****"),
        Line("Opening stream: *****"),
        Line(":: Info message: *****"),
        Line("Done stage: *****"),
        Line("Log message: apple"),
        Line("Log message: *****"),
        Line("Log message: orange"),
        Line("Log message: *****"),
        Line("Emitter: Pausing control of the terminal"),
        Line("Emitter: Resuming control of the terminal"),
    ]
    assert_outputs(
        capsys,
        emit,
        expected_out=expected_out,
        expected_err=expected_err,
        expected_log=expected_log,
    )


@pytest.mark.parametrize("output_is_terminal", [True])
def test_open_stream_no_text(capsys, logger, monkeypatch, init_emitter):
    """Test emitter output when open_stream() has no `text` parameter"""
    monkeypatch.setattr(printer, "_get_terminal_width", lambda: 200)

    emit = Emitter()
    emit.init(EmitterMode.VERBOSE, "testapp", GREETING)

    emit.progress("Begin stage", permanent=False)

    with emit.open_stream() as write_pipe:
        os.write(write_pipe, b"Info message 1\n")
        os.write(write_pipe, b"Info message 2\n")

    emit.progress("End stage", permanent=False)
    emit.ended_ok()

    expected_err = [
        Line("Begin stage"),
        Line(":: Info message 1"),
        Line(":: Info message 2"),
        Line("End stage"),
    ]
    expected_log = expected_err

    assert_outputs(
        capsys,
        emit,
        expected_out=None,
        expected_err=expected_err,
        expected_log=expected_log,
    )
