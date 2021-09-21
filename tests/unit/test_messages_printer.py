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

"""Tests that check the whole _Printer machinery."""

import shutil
import sys
from datetime import datetime

import pytest

from craft_cli import messages
from craft_cli.messages import _MessageInfo, _Printer


@pytest.fixture
def log_filepath(tmp_path):
    """Provide a temporary log file path."""
    return tmp_path / "tempfilepath.log"


# -- simple helpers


def test_terminal_width():
    """Check the terminal width helper."""
    assert messages._get_terminal_width() == shutil.get_terminal_size().columns


# -- tests for the writing line function


def test_writeline_simple_complete(capsys, monkeypatch, log_filepath):
    """Complete verification of _write_line for a simple case."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line(msg)
    assert printer.unfinished_stream == sys.stdout

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert out == test_text + " " * (39 - len(test_text))


def test_writeline_simple_too_long(capsys, monkeypatch, log_filepath):
    """A permanent message that exceeds the line length."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 20)
    printer = _Printer(log_filepath)

    test_text = "012345678901234567890123456789"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line(msg)
    assert printer.unfinished_stream == sys.stdout

    out, err = capsys.readouterr()
    assert not err

    # output is NOT truncated, and it's completed so the cursor at the second line is still
    # to the right
    assert len(out) == 39  # two lines, minus the cursor in the second line
    assert out == test_text + " " * 9


def test_writeline_different_stream(capsys, monkeypatch, log_filepath):
    """Use a different stream."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)

    test_text = "test text"
    msg = _MessageInfo(sys.stderr, test_text)
    printer._write_line(msg)
    assert printer.unfinished_stream == sys.stderr

    out, err = capsys.readouterr()
    assert not out

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert err == test_text + " " * (39 - len(test_text))


def test_writeline_with_timestamp(capsys, monkeypatch, log_filepath):
    """A timestamp was indicated to use."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)

    fake_now = datetime(2009, 9, 1, 12, 13, 15, 123456)
    msg = _MessageInfo(sys.stdout, "test text", use_timestamp=True, created_at=fake_now)
    printer._write_line(msg)

    out, _ = capsys.readouterr()

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    expected_text = "2009-09-01 12:13:15.123 test text"
    assert out == expected_text + " " * (39 - len(expected_text))


def test_writeline_having_previous_message_out(capsys, monkeypatch, log_filepath):
    """There is a previous message to be completed (in stdout)."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text")

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line(msg)

    # stdout has the expected text but with an extra newline before
    out, err = capsys.readouterr()
    assert out == "\n" + test_text + " " * (39 - len(test_text))
    assert not err


def test_writeline_having_previous_message_err(capsys, monkeypatch, log_filepath):
    """There is a previous message to be completed (in stderr)."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stderr, "previous text")

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line(msg)

    # stdout just has the expected text, and an extra newline was sent to stderr
    out, err = capsys.readouterr()
    assert out == test_text + " " * (39 - len(test_text))
    assert err == "\n"


def test_writeline_having_previous_message_complete(capsys, monkeypatch, log_filepath):
    """There is a previous message which is already complete."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text", end_line=True)

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line(msg)

    # stdout has the expected text without anything extra
    out, err = capsys.readouterr()
    assert out == test_text + " " * (39 - len(test_text))
    assert not err


def test_writeline_indicated_to_complete(capsys, monkeypatch, log_filepath):
    """The message is indicated to complete the line."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text, end_line=True)
    printer._write_line(msg)

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # WITH a finishing newline
    assert out == test_text + " " * (39 - len(test_text)) + "\n"


def test_writeline_ephemeral_message_short(capsys, monkeypatch, log_filepath):
    """Complete verification of _write_line for a simple case."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line(msg)
    assert printer.unfinished_stream == sys.stdout

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert out == test_text + " " * (39 - len(test_text))


def test_writeline_ephemeral_message_too_long(capsys, monkeypatch, log_filepath):
    """Complete verification of _write_line for a simple case."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 20)
    printer = _Printer(log_filepath)

    test_text = "0123456789012345678901234567890"
    msg = _MessageInfo(sys.stdout, test_text, ephemeral=True)
    printer._write_line(msg)
    assert printer.unfinished_stream == sys.stdout

    out, err = capsys.readouterr()
    assert not err

    # output is truncated (with an extra ellipsis), still leaving space for the cursor
    assert len(out) == 19
    assert out == "012345678901234567…"


def test_writeline_having_previous_message_ephemeral(capsys, monkeypatch, log_filepath):
    """There is a previous message to be overwritten."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text", ephemeral=True)

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line(msg)

    # stdout has the expected text but with a carriage return before
    out, err = capsys.readouterr()
    assert out == "\r" + test_text + " " * (39 - len(test_text))
    assert not err


# -- tests for the writing bar function


def test_writebar_simple(capsys, monkeypatch, log_filepath):
    """Complete verification of _write_line for a simple case."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=50, bar_total=100)
    printer._write_bar(msg)
    assert printer.unfinished_stream == sys.stdout

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert len(out) == 39
    assert out == "test text [██████████          ] 50/100"


def test_writebar_simple_empty(capsys, monkeypatch, log_filepath):
    """The indicated progress is zero."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=0, bar_total=100)
    printer._write_bar(msg)

    out, _ = capsys.readouterr()
    assert len(out) == 39
    assert out == "test text [                     ] 0/100"


def test_writebar_simple_total(capsys, monkeypatch, log_filepath):
    """The indicated progress is the total."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=100, bar_total=100)
    printer._write_bar(msg)

    out, _ = capsys.readouterr()
    assert len(out) == 39
    assert out == "test text [███████████████████] 100/100"


def test_writebar_simple_exceeding(capsys, monkeypatch, log_filepath):
    """The indicated progress exceeds the total."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=120, bar_total=100)
    printer._write_bar(msg)

    out, _ = capsys.readouterr()
    assert len(out) == 39
    assert out == "test text [███████████████████] 120/100"


def test_writebar_too_long_text(capsys, monkeypatch, log_filepath):
    """No space for the bar because the text is too long."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 20)
    printer = _Printer(log_filepath)

    test_text = "012345678901234567890123456789"
    msg = _MessageInfo(sys.stdout, test_text, bar_progress=20, bar_total=100)
    printer._write_bar(msg)

    out, _ = capsys.readouterr()
    assert len(out) == 19
    assert out == "0123456789012345678"


def test_writebar_too_long_artifacts(capsys, monkeypatch, log_filepath):
    """No space for the bar with all proper artifacts."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 20)
    printer = _Printer(log_filepath)

    test_text = "01234567890123456"  # this would really fit
    msg = _MessageInfo(sys.stdout, test_text, bar_progress=2000, bar_total=100000)  # big numbers!
    printer._write_bar(msg)

    out, _ = capsys.readouterr()
    assert out == "01234567890123456"  # just the message, no space for "a whole progress bar"


def test_writebar_different_stream(capsys, monkeypatch, log_filepath):
    """Use a different stream."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)

    msg = _MessageInfo(sys.stderr, "test text", bar_progress=50, bar_total=100)
    printer._write_bar(msg)
    assert printer.unfinished_stream == sys.stderr

    out, err = capsys.readouterr()
    assert not out

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert err == "test text [██████████          ] 50/100"


def test_writebar_having_previous_message_out(capsys, monkeypatch, log_filepath):
    """There is a previous message to be completed (in stdout)."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text")

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=50, bar_total=100)
    printer._write_bar(msg)

    # stdout has the expected text but with an extra newline before
    out, err = capsys.readouterr()
    assert out == "\ntest text [██████████          ] 50/100"
    assert not err


def test_writebar_having_previous_message_err(capsys, monkeypatch, log_filepath):
    """There is a previous message to be completed (in stderr)."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stderr, "previous text")

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=50, bar_total=100)
    printer._write_bar(msg)

    # stdout just has the expected text, and an extra newline was sent to stderr
    out, err = capsys.readouterr()
    assert out == "test text [██████████          ] 50/100"
    assert err == "\n"


def test_writebar_having_previous_message_complete(capsys, monkeypatch, log_filepath):
    """There is a previous message which is already complete."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text", end_line=True)

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=50, bar_total=100)
    printer._write_bar(msg)

    # stdout has the expected text without anything extra
    out, err = capsys.readouterr()
    assert out == "test text [██████████          ] 50/100"
    assert not err


def test_writebar_having_previous_message_ephemeral(capsys, monkeypatch, log_filepath):
    """There is a previous message to be overwritten."""
    monkeypatch.setattr(messages, "_get_terminal_width", lambda: 40)
    printer = _Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text", ephemeral=True)

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=50, bar_total=100)
    printer._write_bar(msg)

    # stdout has the expected text but with a carriage return before
    out, err = capsys.readouterr()
    assert out == "\rtest text [██████████          ] 50/100"
    assert not err


# -- tests for the logging handling


def test_logfile_opened(log_filepath):
    """The logfile is properly opened."""
    printer = _Printer(log_filepath)
    assert not printer.log.closed
    assert printer.log.mode == "wt"
    assert printer.log.encoding == "utf8"


def test_logfile_closed(log_filepath):
    """The logfile is properly closed."""
    printer = _Printer(log_filepath)
    printer.stop()
    assert printer.log.closed


def test_logfile_used(log_filepath):
    """A message was logged to the file."""
    printer = _Printer(log_filepath)

    fake_now = datetime(2009, 9, 1, 12, 13, 15, 123456)
    msg = _MessageInfo(sys.stdout, "test text", use_timestamp=True, created_at=fake_now)
    printer._log(msg)
    printer.stop()

    assert log_filepath.read_text() == "2009-09-01 12:13:15.123 test text\n"


# -- tests for message showing external API


class RecordingPrinter(_Printer):
    """A Printer isolated from outputs.

    Instead, it records all messages to print.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.written_lines = []
        self.written_bars = []
        self.logged = []

    def _write_line(self, message):
        """Overwrite the real one to avoid it and record the message."""
        self.written_lines.append(message)

    def _write_bar(self, message):
        """Overwrite the real one to avoid it and record the message."""
        self.written_bars.append(message)

    def _log(self, message):
        """Overwrite the real one to avoid it and record the message."""
        self.logged.append(message)


@pytest.fixture
def recording_printer(tmp_path):
    """Provide a recording printer."""
    return RecordingPrinter(tmp_path / "test.log")


def test_show_defaults_no_stream(recording_printer):
    """Write a message with all defaults (without a stream)."""
    before = datetime.now()
    recording_printer.show(None, "test text")

    # check message logged
    (msg,) = recording_printer.logged  # pylint: disable=unbalanced-tuple-unpacking
    assert msg.stream is None
    assert msg.text == "test text"
    assert msg.use_timestamp is False
    assert msg.end_line is False
    assert before <= msg.created_at <= datetime.now()
    assert msg.bar_progress is None
    assert msg.bar_total is None

    # no stream, the message si not sent to screen
    assert not recording_printer.written_lines
    assert not recording_printer.written_bars

    # check nothing was stored (as was not sent to the screen)
    assert recording_printer.prv_msg is None


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_show_defaults(stream, recording_printer):
    """Write a message with all defaults (for the different valid streams)."""
    before = datetime.now()
    recording_printer.show(stream, "test text")

    # check message written
    assert not recording_printer.written_bars
    (msg,) = recording_printer.written_lines  # pylint: disable=unbalanced-tuple-unpacking
    assert msg.stream == stream
    assert msg.text == "test text"
    assert msg.use_timestamp is False
    assert msg.end_line is False
    assert msg.ephemeral is False
    assert before <= msg.created_at <= datetime.now()
    assert msg.bar_progress is None
    assert msg.bar_total is None

    # check it was properly stored for the future
    assert recording_printer.prv_msg is msg  # verify it's the same (not rebuilt) for timestamp

    # check it was also logged
    (logged,) = recording_printer.logged
    assert msg is logged


def test_show_use_timestamp(recording_printer):
    """Control on message's use_timestamp flag."""
    recording_printer.show(sys.stdout, "test text", use_timestamp=True)
    (msg,) = recording_printer.written_lines  # pylint: disable=unbalanced-tuple-unpacking
    assert msg.use_timestamp is True


def test_show_end_line(recording_printer):
    """Control on message's end_line flag."""
    recording_printer.show(sys.stdout, "test text", end_line=True)
    (msg,) = recording_printer.written_lines  # pylint: disable=unbalanced-tuple-unpacking
    assert msg.end_line is True


def test_show_avoid_logging(recording_printer):
    """Control if some message should avoid being logged."""
    recording_printer.show(sys.stdout, "test text", avoid_logging=True)
    assert not recording_printer.logged


def test_show_ephemeral(recording_printer):
    """Control if some message is ephemeral."""
    recording_printer.show(sys.stdout, "test text", ephemeral=True)
    (msg,) = recording_printer.written_lines  # pylint: disable=unbalanced-tuple-unpacking
    assert msg.ephemeral is True


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_progress_bar_valid_streams(stream, recording_printer):
    """Write a progress bar for the different valid streams."""
    before = datetime.now()
    recording_printer.progress_bar(stream, "test text", 20, 100)

    # check message written
    (msg,) = recording_printer.written_bars  # pylint: disable=unbalanced-tuple-unpacking
    assert msg.stream == stream
    assert msg.text == "test text"
    assert msg.bar_progress == 20
    assert msg.bar_total == 100
    assert msg.use_timestamp is False
    assert msg.end_line is False
    assert msg.ephemeral is True
    assert before <= msg.created_at <= datetime.now()

    # only write_bar was used
    assert not recording_printer.written_lines
    assert not recording_printer.logged

    # check it was properly stored for the future
    assert recording_printer.prv_msg is msg  # verify it's the same (not rebuilt) for timestamp


def test_progress_bar_no_stream(recording_printer):
    """No stream no message."""
    recording_printer.progress_bar(None, "test text", 20, 100)
    assert not recording_printer.written_lines
    assert not recording_printer.written_bars
    assert not recording_printer.logged
    assert recording_printer.prv_msg is None


# -- tests for stopping the printer


def test_stop_streams_ok(capsys, log_filepath):
    """Stopping when all streams complete."""
    printer = _Printer(log_filepath)
    assert printer.unfinished_stream is None
    printer.stop()

    out, err = capsys.readouterr()
    assert not out
    assert not err


def test_stop_streams_unfinished_out(capsys, log_filepath):
    """Stopping when stdout is not complete."""
    printer = _Printer(log_filepath)
    printer.unfinished_stream = sys.stdout
    printer.stop()

    out, err = capsys.readouterr()
    assert out == "\n"
    assert not err


def test_stop_streams_unfinished_err(capsys, log_filepath):
    """Stopping when stderr is not complete."""
    printer = _Printer(log_filepath)
    printer.unfinished_stream = sys.stderr
    printer.stop()

    out, err = capsys.readouterr()
    assert not out
    assert err == "\n"
