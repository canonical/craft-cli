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
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from craft_cli import messages
from craft_cli.errors import CraftError
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
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: fake_logpath)


@pytest.fixture(autouse=True)
def fix_terminal_width(monkeypatch):
    """Set a very big terminal width so messages are normally not wrapped."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 500)


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
    width = messages._get_terminal_width()
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


def test_00_exposed_api():
    """Verify names are properly exposed."""
    # pylint: disable=import-outside-toplevel
    from craft_cli import emit

    assert isinstance(emit, messages.Emitter)

    from craft_cli import EmitterMode as test_em

    assert test_em is EmitterMode

    from craft_cli import CraftError as test_cs

    assert test_cs is CraftError


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


def test_02_progress_message_quiet(capsys):
    """Show a progress message being in quiet mode."""
    emit = Emitter()
    emit.init(EmitterMode.QUIET, "testapp", GREETING)
    emit.progress("The meaning of life is 42.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42.", permanent=False),
    ]
    assert_outputs(capsys, emit, expected_log=expected)


def test_02_progress_message_normal(capsys):
    """Show a progress message in normal mode."""
    emit = Emitter()
    emit.init(EmitterMode.NORMAL, "testapp", GREETING)
    emit.progress("The meaning of life is 42.")
    emit.progress("Another message.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42.", permanent=False),
        Line("Another message.", permanent=True),  # stays as it's the last message
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_02_progress_message_more_verbose(capsys, mode):
    """Show a progress message in verbore and debug modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    emit.progress("The meaning of life is 42.")
    emit.progress("Another message.")
    emit.ended_ok()

    # ephemeral ends up being ignored, as in verbose and debug no lines are overridden
    expected = [
        Line("The meaning of life is 42.", permanent=True, timestamp=True),
        Line("Another message.", permanent=True, timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


def test_03_progress_bar_quiet(capsys):
    """Show a progress bar when quiet mode."""
    emit = Emitter()
    emit.init(EmitterMode.QUIET, "testapp", GREETING)
    with emit.progress_bar("Uploading stuff", 1788) as progress:
        for uploaded in [700, 700, 388]:
            progress.advance(uploaded)
    emit.ended_ok()

    # nothing to the screen, first line to the log
    expected_log = [
        Line("Uploading stuff"),
    ]
    assert_outputs(capsys, emit, expected_log=expected_log)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.NORMAL,
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_03_progress_bar_other_modes(capsys, mode, monkeypatch):
    """Show a progress bar in regular modes."""
    # fake size so lines to compare are static
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 60)

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
    emit.ended_ok()

    expected_screen = [
        Line("Uploading stuff", permanent=False),
        Line("Uploading stuff [████████████                    ] 700/1788", permanent=False),
        Line("Uploading stuff [████████████████████████       ] 1400/1788", permanent=False),
        Line("Uploading stuff [███████████████████████████████] 1788/1788", permanent=True),
    ]
    expected_log = expected_screen[:1]  # just the first line, no progress in the logs!
    assert_outputs(capsys, emit, expected_err=expected_screen, expected_log=expected_log)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
        EmitterMode.VERBOSE,
    ],
)
def test_04_5_trace_other_modes(capsys, mode, monkeypatch):
    """Internal trace for other modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    emit.trace("The meaning of life is 42.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42.", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_log=expected)


def test_04_5_trace_in_trace(capsys):
    """Internal trace when in trace mode."""
    emit = Emitter()
    emit.init(EmitterMode.TRACE, "testapp", GREETING)
    emit.trace("The meaning of life is 42.")
    emit.ended_ok()

    expected = [
        Line("The meaning of life is 42.", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_04_third_party_output_other_modes(capsys, tmp_path, mode):
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
    emit.init(mode, "testapp", GREETING)
    with emit.open_stream("Testing stream") as stream:
        subprocess.run([sys.executable, script], stdout=stream, stderr=stream, check=True)
    emit.ended_ok()

    expected = [
        Line("Testing stream", timestamp=True),
        Line(":: foobar out", timestamp=True),
        Line(":: foobar err", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_04_third_party_output_verbose(capsys, tmp_path, mode):
    """Manage the streams produced for sub-executions, debug and verbose mode."""
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
        EmitterMode.NORMAL,
    ],
)
def test_05_06_simple_errors_quietly(capsys, mode):
    """Error because of application or external rules, quiet and normal mode."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    error = CraftError(
        "Cannot find config file 'somepath'.",
    )
    emit.error(error)

    expected = [
        Line("Cannot find config file 'somepath'."),
        Line(f"Full execution log: {emit._log_filepath!r}"),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_05_06_simple_errors_verbosely(capsys, mode):
    """Error because of application or external rules, more verbose modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    error = CraftError(
        "Cannot find config file 'somepath'.",
    )
    emit.error(error)

    expected = [
        Line("Cannot find config file 'somepath'.", timestamp=True),
        Line(f"Full execution log: {emit._log_filepath!r}", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_07_error_api_quietly(capsys, mode):
    """Somewhat expected API error, quiet and normal mode."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    full_error = {"message": "Invalid channel.", "code": "BAD-CHANNEL"}
    error = CraftError("Invalid channel.", details=str(full_error))
    emit.error(error)

    expected_err = [Line("Invalid channel."), Line(f"Full execution log: {emit._log_filepath!r}")]
    expected_log = [
        Line("Invalid channel."),
        Line(f"Detailed information: {full_error}"),
        Line(f"Full execution log: {emit._log_filepath!r}"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_err, expected_log=expected_log)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_07_error_api_verbosely(capsys, mode):
    """Somewhat expected API error, more verbose modes."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    full_error = {"message": "Invalid channel.", "code": "BAD-CHANNEL"}
    error = CraftError("Invalid channel.", details=str(full_error))
    emit.error(error)

    expected = [
        Line("Invalid channel.", timestamp=True),
        Line(f"Detailed information: {full_error}", timestamp=True),
        Line(f"Full execution log: {emit._log_filepath!r}", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_08_09_error_unexpected_quietly(capsys, mode):
    """Unexpected error from a 3rd party or application crash, quiet and normal mode."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    try:
        raise ValueError("pumba")
    except ValueError as exc:
        error = CraftError("First message.")
        error.__cause__ = exc
        with patch("craft_cli.messages._get_traceback_lines", return_value=["foo", "bar"]):
            emit.error(error)

    expected_err = [Line("First message."), Line(f"Full execution log: {emit._log_filepath!r}")]
    expected_log = [
        Line("First message."),
        Line("foo"),
        Line("bar"),
        Line(f"Full execution log: {emit._log_filepath!r}"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_err, expected_log=expected_log)


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_08_09_error_unexpected_verbosely(capsys, mode):
    """Unexpected error from a 3rd party or application crash, more verbose modes."""
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
        Line(f"Full execution log: {emit._log_filepath!r}", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


def test_logging_when_quiet(capsys, logger):
    """Handle the different logging levels when in quiet mode."""
    emit = Emitter()
    emit.init(EmitterMode.QUIET, "testapp", GREETING)
    logger.error("--error-- %s", "with args")
    logger.warning("--warning--")
    logger.info("--info--")
    logger.debug("--debug--")
    emit.ended_ok()

    expected_err = [
        Line("--error-- with args"),
        Line("--warning--"),
    ]
    expected_log = expected_err + [
        Line("--info--"),
        Line("--debug--"),
    ]
    assert_outputs(capsys, emit, expected_err=expected_err, expected_log=expected_log)


def test_logging_when_normal(capsys, logger):
    """Handle the different logging levels when in normal mode."""
    emit = Emitter()
    emit.init(EmitterMode.NORMAL, "testapp", GREETING)
    logger.error("--error-- %s", "with args")
    logger.warning("--warning--")
    logger.info("--info--")
    logger.debug("--debug--")
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


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_logging_when_verboseish(capsys, logger, mode):
    """Handle the different logging levels when in normal mode."""
    emit = Emitter()
    emit.init(mode, "testapp", GREETING)
    logger.error("--error-- %s", "with args")
    logger.warning("--warning--")
    logger.info("--info--")
    logger.debug("--debug--")
    emit.ended_ok()

    expected = [
        Line("--error-- with args", timestamp=True),
        Line("--warning--", timestamp=True),
        Line("--info--", timestamp=True),
        Line("--debug--", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)


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
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: different_logpath)

    emit = Emitter()
    emit.init(EmitterMode.NORMAL, "testapp", different_greeting)
    emit.trace("initial trace")
    emit.set_mode(mode)
    emit.trace("second trace")
    emit.message("final message")
    emit.ended_ok()

    expected_out = [
        Line("final message"),
    ]
    expected_log = [
        Line(different_greeting),
        Line("initial trace"),
        Line("second trace"),
        Line("final message"),
    ]
    assert_outputs(capsys, emit, expected_out=expected_out, expected_log=expected_log)


def test_initial_messages_when_verbose(capsys, tmp_path, monkeypatch):
    """Check the initial messages are sent when setting the mode to VERBOSE."""
    # use different greeting and file logpath so we can actually test them
    different_greeting = "different greeting to not be ignored"
    different_logpath = str(tmp_path / "otherfile.log")
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: different_logpath)

    emit = Emitter()
    emit.init(EmitterMode.NORMAL, "testapp", different_greeting)
    emit.trace("initial trace")
    emit.set_mode(EmitterMode.VERBOSE)
    emit.trace("second trace")
    emit.message("final message")
    emit.ended_ok()

    expected_out = [
        Line("final message"),
    ]
    expected_err = [
        Line(different_greeting, timestamp=True),
        Line(f"Logging execution to {different_logpath!r}", timestamp=True),
    ]
    expected_log = [
        Line(different_greeting),
        Line("initial trace"),
        Line("second trace"),
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
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: different_logpath)

    emit = Emitter()
    emit.init(EmitterMode.NORMAL, "testapp", different_greeting)
    emit.trace("initial trace")
    emit.set_mode(EmitterMode.TRACE)
    emit.trace("second trace")
    emit.message("final message")
    emit.ended_ok()

    expected_out = [
        Line("final message"),
    ]
    expected_err = [
        Line(different_greeting, timestamp=True),
        Line(f"Logging execution to {str(different_logpath)!r}", timestamp=True),
        Line("second trace", timestamp=True),
    ]
    expected_log = [
        Line(different_greeting),
        Line("initial trace"),
        Line("second trace"),
        Line("final message"),
    ]
    assert_outputs(
        capsys,
        emit,
        expected_out=expected_out,
        expected_err=expected_err,
        expected_log=expected_log,
    )


def test_logging_after_closing(capsys, logger):
    """We don't control when log messages are generated, be safe with after-stop ones."""
    emit = Emitter()
    emit.init(EmitterMode.VERBOSE, "testapp", GREETING)
    logger.info("info 1")
    emit.ended_ok()
    logger.info("info 2")

    expected = [
        Line("info 1", timestamp=True),
    ]
    assert_outputs(capsys, emit, expected_err=expected, expected_log=expected)
