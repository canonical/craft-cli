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

"""Tests that check the whole Printer machinery."""

import re
import shutil
import sys
import textwrap
import threading
import time
from datetime import datetime

import pytest

from craft_cli import printer as printermod
from craft_cli.printer import Printer, _MessageInfo, _Spinner


@pytest.fixture(autouse=True)
def init_emitter():
    """Disable the automatic init emitter fixture for this entire module."""


@pytest.fixture
def log_filepath(tmp_path):
    """Provide a temporary log file path."""
    return tmp_path / "tempfilepath.log"


@pytest.fixture(autouse=True)
def thread_guard(tmp_path):
    """Ensure that any started spinner is stopped after the test."""
    # let's run the test first
    yield

    # stop all spinner threads
    for thread in threading.enumerate():
        if isinstance(thread, _Spinner):
            thread.stop()


@pytest.fixture(autouse=True)
def clear_stream_is_terminal_cache():
    """Clear the _stream_is_terminal cache before and after tests.

    Otherwise our isatty monkey-patching can either confuse or be confused
    by other tests.
    """
    printermod._stream_is_terminal.cache_clear()
    yield
    printermod._stream_is_terminal.cache_clear()


# -- simple helpers


def test_terminal_width():
    """Check the terminal width helper."""
    assert printermod._get_terminal_width() == shutil.get_terminal_size().columns


def test_streamisterminal_no_isatty_method():
    """The stream does not have an isatty method."""
    stream = object()
    assert not hasattr(stream, "isatty")
    result = printermod._stream_is_terminal(stream)
    assert result is False


def test_streamisterminal_tty_not():
    """The stream is not a terminal."""

    class FakeStream:
        def isatty(self):
            return False

    result = printermod._stream_is_terminal(FakeStream())
    assert result is False


def test_streamisterminal_tty_yes_usable(monkeypatch):
    """The stream is a terminal of use."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)

    class FakeStream:
        def isatty(self):
            return True

    result = printermod._stream_is_terminal(FakeStream())
    assert result is True


def test_streamisterminal_tty_yes_unusable(monkeypatch):
    """The stream is a terminal that cannot really be used (no columns!)."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 0)

    class FakeStream:
        def isatty(self):
            return True

    result = printermod._stream_is_terminal(FakeStream())
    assert result is False


# -- tests for the writing line (terminal version) function


def test_writelineterminal_simple_complete(capsys, monkeypatch, log_filepath):
    """Complete verification of _write_line_terminal for a simple case."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line_terminal(msg)
    assert printer.unfinished_stream == sys.stdout

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert out == test_text + " " * (39 - len(test_text))


def test_writelineterminal_simple_too_long(capsys, monkeypatch, log_filepath):
    """A permanent message that exceeds the line length."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 20)
    printer = Printer(log_filepath)

    test_text = "012345678901234567890123456789"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line_terminal(msg)
    assert printer.unfinished_stream == sys.stdout

    out, err = capsys.readouterr()
    assert not err

    # output is NOT truncated, and it's completed so the cursor at the second line is still
    # to the right
    assert len(out) == 39  # two lines, minus the cursor in the second line
    assert out == test_text + " " * 9


def test_writelineterminal_different_stream(capsys, monkeypatch, log_filepath):
    """Use a different stream."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    test_text = "test text"
    msg = _MessageInfo(sys.stderr, test_text)
    printer._write_line_terminal(msg)
    assert printer.unfinished_stream == sys.stderr

    out, err = capsys.readouterr()
    assert not out

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert err == test_text + " " * (39 - len(test_text))


def test_writelineterminal_with_timestamp(capsys, monkeypatch, log_filepath):
    """A timestamp was indicated to use."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    fake_now = datetime(2009, 9, 1, 12, 13, 15, 123456)
    msg = _MessageInfo(sys.stdout, "test text", use_timestamp=True, created_at=fake_now)
    printer._write_line_terminal(msg)

    out, _ = capsys.readouterr()

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    expected_text = "2009-09-01 12:13:15.123 test text"
    assert out == expected_text + " " * (39 - len(expected_text))


def test_writelineterminal_having_previous_message_out(capsys, monkeypatch, log_filepath):
    """There is a previous message to be completed (in stdout)."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text")

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line_terminal(msg)

    # stdout has the expected text but with an extra newline before
    out, err = capsys.readouterr()
    assert out == "\n" + test_text + " " * (39 - len(test_text))
    assert not err


def test_writelineterminal_having_previous_message_err(capsys, monkeypatch, log_filepath):
    """There is a previous message to be completed (in stderr)."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stderr, "previous text")

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line_terminal(msg)

    # stdout just has the expected text, and an extra newline was sent to stderr
    out, err = capsys.readouterr()
    assert out == test_text + " " * (39 - len(test_text))
    assert err == "\n"


def test_writelineterminal_having_previous_message_complete(capsys, monkeypatch, log_filepath):
    """There is a previous message which is already complete."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text", end_line=True)

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line_terminal(msg)

    # stdout has the expected text without anything extra
    out, err = capsys.readouterr()
    assert out == test_text + " " * (39 - len(test_text))
    assert not err


def test_writelineterminal_indicated_to_complete(capsys, monkeypatch, log_filepath):
    """The message is indicated to complete the line."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text, end_line=True)
    printer._write_line_terminal(msg)

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # WITH a finishing newline
    assert out == test_text + " " * (39 - len(test_text)) + "\n"


def test_writelineterminal_ephemeral_message_short(capsys, monkeypatch, log_filepath):
    """Complete verification of _write_line_terminal for a simple case."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line_terminal(msg)
    assert printer.unfinished_stream == sys.stdout

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert out == test_text + " " * (39 - len(test_text))


def test_writelineterminal_ephemeral_message_too_long(capsys, monkeypatch, log_filepath):
    """Complete verification of _write_line_terminal for a simple case."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 20)
    printer = Printer(log_filepath)

    test_text = "0123456789012345678901234567890"
    msg = _MessageInfo(sys.stdout, test_text, ephemeral=True)
    printer._write_line_terminal(msg)
    assert printer.unfinished_stream == sys.stdout

    out, err = capsys.readouterr()
    assert not err

    # output is truncated (with an extra ellipsis), still leaving space for the cursor
    assert len(out) == 19
    assert out == "012345678901234567…"


def test_writelineterminal_having_previous_message_ephemeral(capsys, monkeypatch, log_filepath):
    """There is a previous message to be overwritten."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text", ephemeral=True)

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line_terminal(msg)

    # stdout has the expected text but with a carriage return before
    out, err = capsys.readouterr()
    assert out == "\r" + test_text + " " * (39 - len(test_text))
    assert not err


@pytest.mark.parametrize(
    "prv_msg",
    [
        None,
        _MessageInfo(sys.stdout, "previous text", end_line=True),
        _MessageInfo(sys.stdout, "previous text", ephemeral=True),
    ],
)
def test_writelineterminal_spintext_simple(capsys, monkeypatch, log_filepath, prv_msg):
    """A message with spintext."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)
    printer.prv_msg = prv_msg  # will overwrite previous message not matter what

    msg = _MessageInfo(sys.stdout, "test text")
    printer._write_line_terminal(msg, spintext=" * 3.15s")

    # stdout has the expected text, overwriting previous message, with the spin text at the end
    out, err = capsys.readouterr()
    assert len(out) == 40  # the CR + the regular 39 chars
    assert out == "\rtest text * 3.15s                      "
    assert not err


def test_writelineterminal_spintext_message_too_long(capsys, monkeypatch, log_filepath):
    """A message with spintext that is too long only overwrites the last "real line"."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 20)
    printer = Printer(log_filepath)

    msg = _MessageInfo(sys.stdout, "0.1.2.3.4.5.6.7.8.9.a.b.c.d.e.")
    printer._write_line_terminal(msg, spintext=" * 3.15s")

    out, err = capsys.readouterr()
    assert not err

    # output the last line only (with the spin text, of course)
    assert len(out) == 20  # the CR + the regular 19 chars
    assert out == "\ra.b.c.d.e. * 3.15s "


def test_writelineterminal_spintext_length_just_exceeded(capsys, monkeypatch, log_filepath):
    """A message that would fit, but it just exceeds the line length because of the spin text."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 20)
    printer = Printer(log_filepath)

    msg = _MessageInfo(sys.stdout, "0x1x2x3x4x5x6x7x8x")  # len 16, it would fit!
    printer._write_line_terminal(msg, spintext=" * 3.15s")  # adding this would exceed the length

    out, err = capsys.readouterr()
    assert not err

    # the message is slightly truncated so the spin text does not trigger a multiline situation
    assert len(out) == 20  # the CR + the regular 19 chars
    assert out == "\r0x1x2x3x4x… * 3.15s"


@pytest.mark.parametrize("test_text", ["", "Some test text."])
def test_writelineterminal_ephemeral_spam(capsys, monkeypatch, log_filepath, test_text):
    """Spam _write_line_terminal with the same message over and over."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    for _ in range(10):
        # Recreate the message here so we're checking equality, not just identity.
        msg = _MessageInfo(sys.stdout, test_text, end_line=False, ephemeral=True)
        printer._write_line_terminal(msg)
        printer.prv_msg = msg

    assert printer.unfinished_stream == sys.stdout

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    # There will only be one copy of the text.
    assert out == test_text[:40] + " " * (39 - len(test_text))


@pytest.mark.parametrize(("ephemeral", "end_line"), [(False, False), (False, True), (True, True)])
@pytest.mark.parametrize("text", ["", "Some test text"])
def test_writelineterminal_rewrites_same_message(
    capsys, monkeypatch, log_filepath, text, ephemeral, end_line
):
    """Spam _write_line_terminal with the same message and ensure it keeps writing."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    for _ in range(10):
        message = _MessageInfo(sys.stdout, text, ephemeral=ephemeral, end_line=end_line)
        printer._write_line_terminal(message)
        printer.prv_msg = message

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert out.strip() == "\n".join([text + " " * (39 - len(text))] * 10).strip()


@pytest.mark.parametrize("ephemeral", [True, False])
@pytest.mark.parametrize("text", ["", "Some test text"])
@pytest.mark.parametrize(
    "spintext",
    [
        "!!!!!!!!!!",
        "\\|/-",
        "1234567890",
    ],
)
def test_writelineterminal_rewrites_same_message_with_spintext(
    capsys, monkeypatch, log_filepath, text, spintext, ephemeral
):
    """Spam _write_line_terminal with the same message over and over."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    for spin in spintext:
        message = _MessageInfo(sys.stdout, text, ephemeral=ephemeral, end_line=False)
        printer._write_line_terminal(message, spintext=spin)
        printer.prv_msg = message

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    expected = "\r".join(text + s + " " * (39 - len(text) - len(s)) for s in spintext)
    assert out.strip() == expected.strip()


# -- tests for the writing line (captured version) function


@pytest.mark.parametrize(
    "test_text",
    [
        "test text",
        "012345678901234567890123456789",
        "a very long, long text -" * 20,
    ],
)
def test_writelinecaptured_simple_complete(capsys, monkeypatch, log_filepath, test_text):
    """Complete verification of _write_line_captured several text cases."""
    printer = Printer(log_filepath)

    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line_captured(msg)
    assert printer.unfinished_stream is None

    out, err = capsys.readouterr()
    assert not err

    # output is just the text with the finishing newline
    assert out == test_text + "\n"


def test_writelinecaptured_with_timestamp(capsys, monkeypatch, log_filepath):
    """A timestamp was indicated to use."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    fake_now = datetime(2009, 9, 1, 12, 13, 15, 123456)
    msg = _MessageInfo(sys.stdout, "test text", use_timestamp=True, created_at=fake_now)
    printer._write_line_captured(msg)

    out, _ = capsys.readouterr()

    # output is just the timestamp and the text with the finishing newline
    assert out == "2009-09-01 12:13:15.123 test text\n"


# -- tests for the writing bar (terminal version) function


def test_writebarterminal_simple(capsys, monkeypatch, log_filepath):
    """Complete verification of _write_bar_terminal for a simple case."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=50, bar_total=100)
    printer._write_bar_terminal(msg)
    assert printer.unfinished_stream == sys.stdout

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert len(out) == 39
    assert out == "test text [██████████          ] 50/100"


def test_writebarterminal_timestamp(capsys, monkeypatch, log_filepath):
    """A timestamp was indicated to use."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 60)
    printer = Printer(log_filepath)

    fake_now = datetime(2009, 9, 1, 12, 13, 15, 123456)
    msg = _MessageInfo(
        sys.stdout,
        "test text",
        bar_progress=50,
        bar_total=100,
        use_timestamp=True,
        created_at=fake_now,
    )
    printer._write_bar_terminal(msg)
    assert printer.unfinished_stream == sys.stdout

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert len(out) == 59
    assert out == "2009-09-01 12:13:15.123 test text [████████        ] 50/100"


def test_writebarterminal_simple_empty(capsys, monkeypatch, log_filepath):
    """The indicated progress is zero."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=0, bar_total=100)
    printer._write_bar_terminal(msg)

    out, _ = capsys.readouterr()
    assert len(out) == 39
    assert out == "test text [                     ] 0/100"


def test_writebarterminal_simple_total(capsys, monkeypatch, log_filepath):
    """The indicated progress is the total."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=100, bar_total=100)
    printer._write_bar_terminal(msg)

    out, _ = capsys.readouterr()
    assert len(out) == 39
    assert out == "test text [███████████████████] 100/100"


def test_writebarterminal_simple_exceeding(capsys, monkeypatch, log_filepath):
    """The indicated progress exceeds the total."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=120, bar_total=100)
    printer._write_bar_terminal(msg)

    out, _ = capsys.readouterr()
    assert len(out) == 39
    assert out == "test text [███████████████████] 120/100"


def test_writebarterminal_too_long_text(capsys, monkeypatch, log_filepath):
    """No space for the bar because the text is too long."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 20)
    printer = Printer(log_filepath)

    test_text = "012345678901234567890123456789"
    msg = _MessageInfo(sys.stdout, test_text, bar_progress=20, bar_total=100)
    printer._write_bar_terminal(msg)

    out, _ = capsys.readouterr()
    assert len(out) == 19
    assert out == "0123456789012345678"


def test_writebarterminal_too_long_artifacts(capsys, monkeypatch, log_filepath):
    """No space for the bar with all proper artifacts."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 20)
    printer = Printer(log_filepath)

    test_text = "01234567890123456"  # this would really fit
    msg = _MessageInfo(sys.stdout, test_text, bar_progress=2000, bar_total=100000)  # big numbers!
    printer._write_bar_terminal(msg)

    out, _ = capsys.readouterr()
    assert out == "01234567890123456"  # just the message, no space for "a whole progress bar"


def test_writebarterminal_different_stream(capsys, monkeypatch, log_filepath):
    """Use a different stream."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)

    msg = _MessageInfo(sys.stderr, "test text", bar_progress=50, bar_total=100)
    printer._write_bar_terminal(msg)
    assert printer.unfinished_stream == sys.stderr

    out, err = capsys.readouterr()
    assert not out

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert err == "test text [██████████          ] 50/100"


def test_writebarterminal_having_previous_message_out(capsys, monkeypatch, log_filepath):
    """There is a previous message to be completed (in stdout)."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text")

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=50, bar_total=100)
    printer._write_bar_terminal(msg)

    # stdout has the expected text but with an extra newline before
    out, err = capsys.readouterr()
    assert out == "\ntest text [██████████          ] 50/100"
    assert not err


def test_writebarterminal_having_previous_message_err(capsys, monkeypatch, log_filepath):
    """There is a previous message to be completed (in stderr)."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stderr, "previous text")

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=50, bar_total=100)
    printer._write_bar_terminal(msg)

    # stdout just has the expected text, and an extra newline was sent to stderr
    out, err = capsys.readouterr()
    assert out == "test text [██████████          ] 50/100"
    assert err == "\n"


def test_writebarterminal_having_previous_message_complete(capsys, monkeypatch, log_filepath):
    """There is a previous message which is already complete."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text", end_line=True)

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=50, bar_total=100)
    printer._write_bar_terminal(msg)

    # stdout has the expected text without anything extra
    out, err = capsys.readouterr()
    assert out == "test text [██████████          ] 50/100"
    assert not err


def test_writebarterminal_having_previous_message_ephemeral(capsys, monkeypatch, log_filepath):
    """There is a previous message to be overwritten."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 40)
    printer = Printer(log_filepath)
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text", ephemeral=True)

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=50, bar_total=100)
    printer._write_bar_terminal(msg)

    # stdout has the expected text but with a carriage return before
    out, err = capsys.readouterr()
    assert out == "\rtest text [██████████          ] 50/100"
    assert not err


# -- tests for the writing bar (captured version) function


def test_writebarcaptured_simple(capsys, monkeypatch, log_filepath):
    """Complete verification of _write_bar_captured for a simple case."""
    printer = Printer(log_filepath)

    msg = _MessageInfo(sys.stdout, "test text", bar_progress=50, bar_total=100)
    printer._write_bar_captured(msg)
    assert printer.unfinished_stream is None

    out, err = capsys.readouterr()
    assert not err
    assert not out


# -- tests for the logging handling


def test_logfile_opened(log_filepath):
    """The logfile is properly opened."""
    printer = Printer(log_filepath)
    assert not printer.log.closed
    assert printer.log.mode == "at"
    assert printer.log.encoding == "utf8"


def test_logfile_closed(log_filepath):
    """The logfile is properly closed."""
    printer = Printer(log_filepath)
    printer.stop()
    assert printer.log.closed


def test_logfile_used(log_filepath):
    """A message was logged to the file."""
    printer = Printer(log_filepath)

    fake_now = datetime(2009, 9, 1, 12, 13, 15, 123456)
    msg = _MessageInfo(sys.stdout, "test text", use_timestamp=True, created_at=fake_now)
    printer._log(msg)
    printer.stop()

    assert log_filepath.read_text() == "2009-09-01 12:13:15.123 test text\n"


def test_logfile_flush(log_filepath, mocker):
    """Printer flushes the log file after every write."""
    printer = Printer(log_filepath)

    fake_now = datetime(2009, 9, 1, 12, 13, 15, 123456)
    msg = _MessageInfo(None, "test text", created_at=fake_now)

    flush = mocker.spy(printer.log, "flush")
    assert flush.call_count == 0
    printer._log(msg)
    assert flush.call_count == 1
    printer._log(msg)
    assert flush.call_count == 2

    printer.stop()
    assert log_filepath.read_text() == textwrap.dedent(
        """\
        2009-09-01 12:13:15.123 test text
        2009-09-01 12:13:15.123 test text
        """
    )


# -- tests for message showing external API


def test_show_defaults_no_stream(recording_printer):
    """Write a message with all defaults (without a stream)."""
    before = datetime.now()
    recording_printer.show(None, "test text")

    # check message logged
    (msg,) = recording_printer.logged
    assert msg.stream is None
    assert msg.text == "test text"
    assert msg.use_timestamp is False
    assert msg.end_line is False
    assert before <= msg.created_at <= datetime.now()
    assert msg.bar_progress is None
    assert msg.bar_total is None

    # no stream, the message si not sent
    assert not recording_printer.written_terminal_lines
    assert not recording_printer.written_terminal_bars
    assert not recording_printer.written_captured_lines
    assert not recording_printer.written_captured_bars

    # check nothing was stored (as was not sent to the screen)
    assert recording_printer.prv_msg is None

    # the spinner didn't receive anything
    assert not recording_printer.spinner.supervised


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_show_defaults_terminal(stream, monkeypatch, recording_printer):
    """Write a message with all defaults (for the different valid streams), having a terminal."""
    monkeypatch.setattr(stream, "isatty", lambda: True)
    before = datetime.now()
    recording_printer.show(stream, "test text")

    # check message written
    assert not recording_printer.written_terminal_bars
    assert not recording_printer.written_captured_bars
    assert not recording_printer.written_captured_lines
    (msg,) = recording_printer.written_terminal_lines
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

    # the spinner now has the shown message to supervise
    assert recording_printer.spinner.supervised == [msg]


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_show_defaults_captured(stream, monkeypatch, recording_printer):
    """Write a message with all defaults (for the different valid streams), captured output."""
    monkeypatch.setattr(stream, "isatty", lambda: False)
    before = datetime.now()
    recording_printer.show(stream, "test text")

    # check message written
    assert not recording_printer.written_terminal_bars
    assert not recording_printer.written_captured_bars
    assert not recording_printer.written_terminal_lines
    (msg,) = recording_printer.written_captured_lines
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

    # the spinner now has the shown message to supervise
    assert recording_printer.spinner.supervised == [msg]


def test_show_use_timestamp(recording_printer, monkeypatch):
    """Control on message's use_timestamp flag."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    recording_printer.show(sys.stdout, "test text", use_timestamp=True)
    (msg,) = recording_printer.written_terminal_lines
    assert msg.use_timestamp is True


def test_show_end_line(recording_printer, monkeypatch):
    """Control on message's end_line flag."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    recording_printer.show(sys.stdout, "test text", end_line=True)
    (msg,) = recording_printer.written_terminal_lines
    assert msg.end_line is True


def test_show_avoid_logging(recording_printer, monkeypatch):
    """Control if some message should avoid being logged."""
    recording_printer.show(sys.stdout, "test text", avoid_logging=True)
    assert not recording_printer.logged


def test_show_ephemeral(recording_printer, monkeypatch):
    """Control if some message is ephemeral."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    recording_printer.show(sys.stdout, "test text", ephemeral=True)
    (msg,) = recording_printer.written_terminal_lines
    assert msg.ephemeral is True


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_progress_bar_valid_streams_terminal(stream, recording_printer, monkeypatch):
    """Write a progress bar for the different valid streams, having a terminal."""
    monkeypatch.setattr(stream, "isatty", lambda: True)

    # set a message in the spinner, to check that writing a progress bar will remove it
    recording_printer.spinner.prv_msg = _MessageInfo(sys.stdout, "test text")

    before = datetime.now()
    recording_printer.progress_bar(
        stream, "test text", progress=20, total=100, use_timestamp=False
    )

    # check message written
    assert not recording_printer.written_terminal_lines
    assert not recording_printer.written_captured_lines
    assert not recording_printer.written_captured_bars
    assert not recording_printer.logged
    (msg,) = recording_printer.written_terminal_bars
    assert msg.stream == stream
    assert msg.text == "test text"
    assert msg.bar_progress == 20
    assert msg.bar_total == 100
    assert msg.use_timestamp is False
    assert msg.end_line is False
    assert msg.ephemeral is True
    assert before <= msg.created_at <= datetime.now()

    # check it was properly stored for the future
    assert recording_printer.prv_msg is msg  # verify it's the same (not rebuilt) for timestamp

    # the spinner message was removed
    assert recording_printer.spinner.supervised == [None]


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_progress_bar_valid_streams_captured(stream, recording_printer, monkeypatch):
    """Write a progress bar for the different valid streams, captured output."""
    monkeypatch.setattr(stream, "isatty", lambda: False)

    # set a message in the spinner, to check that writing a progress bar will remove it
    recording_printer.spinner.prv_msg = _MessageInfo(sys.stdout, "test text")

    before = datetime.now()
    recording_printer.progress_bar(
        stream, "test text", progress=20, total=100, use_timestamp=False
    )

    # check message written
    assert not recording_printer.written_terminal_lines
    assert not recording_printer.written_captured_lines
    assert not recording_printer.written_terminal_bars
    assert not recording_printer.logged
    (msg,) = recording_printer.written_captured_bars
    assert msg.stream == stream
    assert msg.text == "test text"
    assert msg.bar_progress == 20
    assert msg.bar_total == 100
    assert msg.use_timestamp is False
    assert msg.end_line is False
    assert msg.ephemeral is True
    assert before <= msg.created_at <= datetime.now()

    # check it was properly stored for the future
    assert recording_printer.prv_msg is msg  # verify it's the same (not rebuilt) for timestamp

    # the spinner message was removed
    assert recording_printer.spinner.supervised == [None]


@pytest.mark.parametrize("isatty", [True, False])
def test_spin(isatty, monkeypatch, recording_printer):
    """Write a message using a spin text."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: isatty)
    msg = _MessageInfo(sys.stdout, "test text")
    spin_text = "test spint text"
    recording_printer.spin(msg, spin_text)

    # check message written
    assert not recording_printer.written_terminal_bars
    if isatty:
        assert len(recording_printer.written_terminal_lines) == 1
        written_msg, written_spintext = recording_printer.written_terminal_lines[0]
        assert written_msg is msg
        assert written_spintext is spin_text
    else:
        assert len(recording_printer.written_terminal_lines) == 0


def test_progress_bar_no_stream(recording_printer):
    """No stream no message."""
    recording_printer.progress_bar(None, "test text", progress=20, total=100, use_timestamp=False)
    assert not recording_printer.written_terminal_lines
    assert not recording_printer.written_terminal_bars
    assert not recording_printer.written_captured_lines
    assert not recording_printer.written_captured_bars
    assert not recording_printer.logged
    assert recording_printer.prv_msg is None


def test_show_when_stopped(recording_printer):
    """Noop after stopping."""
    recording_printer.stop()
    recording_printer.show(None, "test text")

    # nothing is done
    assert not recording_printer.logged
    assert not recording_printer.written_terminal_lines
    assert not recording_printer.written_terminal_bars
    assert not recording_printer.written_captured_lines
    assert not recording_printer.written_captured_bars
    assert recording_printer.prv_msg is None
    assert not recording_printer.spinner.supervised


# -- tests for starting/stopping the printer


def test_init_printer_ok(log_filepath):
    """Printer is initiated as usual."""
    printer = Printer(log_filepath)
    assert printer.spinner.is_alive()


def test_init_printer_testmode(log_filepath, monkeypatch):
    """Printer is initiated as usual."""
    monkeypatch.setattr(printermod, "TESTMODE", True)
    printer = Printer(log_filepath)
    assert not printer.spinner.is_alive()


def test_stop_streams_ok(capsys, log_filepath):
    """Stopping when all streams complete."""
    printer = Printer(log_filepath)
    assert printer.unfinished_stream is None
    printer.stop()

    out, err = capsys.readouterr()
    assert not out
    assert not err


def test_stop_streams_unfinished_out_non_ephemeral(capsys, log_filepath, monkeypatch):
    """Stopping when stdout is not complete."""
    printer = Printer(log_filepath)
    printer.unfinished_stream = sys.stdout
    printer.prv_msg = _MessageInfo(sys.stdout, "test")
    printer.stop()

    out, err = capsys.readouterr()
    assert out == "\n"
    assert not err


def test_stop_streams_unfinished_out_ephemeral(capsys, log_filepath, monkeypatch):
    """Stopping when stdout is not complete."""
    monkeypatch.setattr(printermod, "_get_terminal_width", lambda: 10)
    printer = Printer(log_filepath)
    printer.unfinished_stream = sys.stdout
    printer.prv_msg = _MessageInfo(sys.stdout, "test", ephemeral=True)
    printer.stop()

    out, err = capsys.readouterr()
    assert out == "\r         \r"  # 9 spaces
    assert not err


def test_stop_streams_unfinished_err(capsys, log_filepath):
    """Stopping when stderr is not complete."""
    printer = Printer(log_filepath)
    printer.unfinished_stream = sys.stderr
    printer.prv_msg = _MessageInfo(sys.stderr, "test")
    printer.stop()

    out, err = capsys.readouterr()
    assert not out
    assert err == "\n"


def test_stop_spinner_ok(log_filepath):
    """Stop the spinner."""
    printer = Printer(log_filepath)
    assert printer.spinner.is_alive()
    printer.stop()
    assert not printer.spinner.is_alive()


def test_stop_spinner_testmode(log_filepath, monkeypatch):
    """Stop the spinner."""
    monkeypatch.setattr(printermod, "TESTMODE", True)
    printer = Printer(log_filepath)
    printer.stop()
    assert not printer.spinner.is_alive()


# -- tests for the _Spinner class


class RecordingPrinter(Printer):
    """A Printer isolated from outputs; just records spin calls."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.spinned = []

    def spin(self, message, spintext):
        """Overwrite the real one to avoid it and record the message."""
        self.spinned.append((message, spintext))


@pytest.fixture
def spinner(tmp_path):
    """Provide a spinner easy to test.

    Two characteristics:
    - we'll ensure it is stopped
    - use a fake Printer so we can assert on "spin" calls
    """
    spinner = _Spinner(RecordingPrinter(tmp_path / "test.log"))
    spinner.start()
    try:
        yield spinner
    finally:
        spinner.stop()


def test_spinner_daemon(spinner):
    """It should be a daemon."""
    assert spinner.daemon


def test_spinner_working_simple(spinner, monkeypatch):
    """The spinner at work."""
    # set absurdly low times so we can have several spin texts in the test
    monkeypatch.setattr(printermod, "_SPINNER_THRESHOLD", 0.001)
    monkeypatch.setattr(printermod, "_SPINNER_DELAY", 0.001)

    # send a message, wait enough until we have enough spinned to test, and turn it off
    msg = _MessageInfo(sys.stdout, "test msg")
    spinner.supervise(msg)
    for _ in range(100):
        if len(spinner.printer.spinned) >= 6:
            break
        time.sleep(0.01)
    else:
        pytest.fail("Waited too long for the _Spinner to generate messages")
    spinner.supervise(None)
    to_check = spinner.printer.spinned[:5]

    # check the initial messages complete the "spinner drawing" also showing elapsed time
    spinned_messages, spinned_texts = list(zip(*to_check))
    assert all(spinned_msg is msg for spinned_msg in spinned_messages)
    expected_texts = (
        r" - \(\d\.\ds\)",
        r" \\ \(\d\.\ds\)",
        r" | \(\d\.\ds\)",
        r" / \(\d\.\ds\)",
        r" - \(\d\.\ds\)",
    )
    for expected, real in list(zip(expected_texts, spinned_texts)):
        assert re.match(expected, real)

    # the last message should clean the spinner
    assert spinner.printer.spinned[-1] == (msg, " ")


def test_spinner_spam(spinner, monkeypatch):
    """Test that the spinner works properly when spamming the same message.

    The expected behaviour is to ignore the existence of the fresh message and just
    write when the spinner needs to update.
    """
    # set absurdly low times so we can have several spin texts in the test
    monkeypatch.setattr(printermod, "_SPINNER_THRESHOLD", 0.001)
    monkeypatch.setattr(printermod, "_SPINNER_DELAY", 0.001)

    # send a message, wait enough until we have enough spinned to test, and turn it off
    msg = _MessageInfo(sys.stdout, "test msg")
    for _ in range(100):
        spinner.supervise(_MessageInfo(sys.stdout, "test msg"))
    for _ in range(100):
        if len(spinner.printer.spinned) >= 6:
            break
        time.sleep(0.01)
    else:
        pytest.fail("Waited too long for the _Spinner to generate messages")
    spinner.supervise(None)
    to_check = spinner.printer.spinned[:5]

    # check the initial messages complete the "spinner drawing" also showing elapsed time
    spinned_messages, spinned_texts = list(zip(*to_check))
    assert all(spinned_msg == msg for spinned_msg in spinned_messages)
    expected_texts = (
        r" - \(\d\.\ds\)",
        r" \\ \(\d\.\ds\)",
        r" | \(\d\.\ds\)",
        r" / \(\d\.\ds\)",
        r" - \(\d\.\ds\)",
    )
    for expected, real in list(zip(expected_texts, spinned_texts)):
        assert re.match(expected, real)

    # the last message should clean the spinner
    assert spinner.printer.spinned[-1] == (msg, " ")


def test_spinner_two_messages(spinner, monkeypatch):
    """Two consecutive messages with spinner."""
    # set absurdly low times so we can have several spin texts in the test
    monkeypatch.setattr(printermod, "_SPINNER_THRESHOLD", 0.001)
    monkeypatch.setattr(printermod, "_SPINNER_DELAY", 0.001)

    # send a first message, wait enough until we have enough spinned to test
    msg1 = _MessageInfo(sys.stdout, "test msg 1")
    spinner.supervise(msg1)
    for _ in range(100):
        if len(spinner.printer.spinned) >= 6:
            break
        time.sleep(0.01)
    else:
        pytest.fail("Waited too long for the _Spinner to generate messages")

    # send a second message, wait again, and turn it off
    msg2 = _MessageInfo(sys.stdout, "test msg 2")
    spinner.supervise(msg2)
    first_pass_spinned_length = len(spinner.printer.spinned)
    for _ in range(100):
        if len(spinner.printer.spinned) >= first_pass_spinned_length + 6:
            break
        time.sleep(0.01)
    else:
        pytest.fail("Waited too long for the _Spinner to generate messages")
    spinner.supervise(None)

    # check we have two set of messages
    spinned_1 = [sp_text for sp_msg, sp_text in spinner.printer.spinned if sp_msg == msg1]
    spinned_2 = [sp_text for sp_msg, sp_text in spinner.printer.spinned if sp_msg == msg2]
    assert spinned_1 and spinned_2

    # in both cases, the final message should be to clean the spinner
    assert spinned_1[-1] == " "
    assert spinned_2[-1] == " "


def test_spinner_silent_before_threshold(spinner, monkeypatch):
    """Nothing happens before the threshold time."""
    monkeypatch.setattr(printermod, "_SPINNER_THRESHOLD", 10)
    spinner.supervise(_MessageInfo(sys.stdout, "test msg 1"))
    spinner.supervise(_MessageInfo(sys.stdout, "test msg 2"))
    assert spinner.printer.spinned == []


def test_spinner_in_the_vacuum(spinner, monkeypatch):
    """There is no spinner without a previous message."""
    # set absurdly low times to for the Spinner to start processing
    monkeypatch.setattr(printermod, "_SPINNER_THRESHOLD", 0.001)
    monkeypatch.setattr(printermod, "_SPINNER_DELAY", 0.001)

    # enough time for activation
    time.sleep(0.05)

    # nothing spinned, as no message to spin
    assert spinner.printer.spinned == []


def test_spinner_silent_on_complete_messages(spinner, monkeypatch):
    """Nothing happens before the threshold time."""
    monkeypatch.setattr(printermod, "_SPINNER_THRESHOLD", 0.001)
    spinner.supervise(_MessageInfo(sys.stdout, "test msg 1", end_line=True))

    # enough time for activation
    time.sleep(0.05)

    assert spinner.printer.spinned == []


def test_secrets(capsys, log_filepath):
    printer = Printer(log_filepath)

    secrets = ["banana", "watermelon"]

    message = "apple banana orange watermelon"
    expected = "apple ***** orange *****\n"

    printer.set_secrets(secrets)
    printer.show(sys.stderr, message, avoid_logging=True)

    _, stderr = capsys.readouterr()
    assert stderr == expected


def test_secrets_subwords(capsys, log_filepath):
    printer = Printer(log_filepath)

    secrets = ["range", "term"]

    message = "apple banana orange watermelon"
    # Secrets are replaced "dumbly": they are not expected to be "whole words".
    expected = "apple banana o***** wa*****elon\n"

    printer.set_secrets(secrets)
    printer.show(sys.stderr, message, avoid_logging=True)

    _, stderr = capsys.readouterr()
    assert stderr == expected


def test_secrets_repetitions(capsys, log_filepath):
    printer = Printer(log_filepath)

    secrets = ["range"]

    message = "Free-range strange oranges"
    # Secrets can be replaced multiple times on the same string
    expected = "Free-***** st***** o*****s\n"

    printer.set_secrets(secrets)
    printer.show(sys.stderr, message, avoid_logging=True)

    _, stderr = capsys.readouterr()
    assert stderr == expected


def test_secrets_non_ascii(capsys, log_filepath):
    printer = Printer(log_filepath)

    secrets = ["ação"]

    message = "Ação reação coração"
    # Secrets can be non-ascii words, and match case.
    expected = "Ação re***** cor*****\n"

    printer.set_secrets(secrets)
    printer.show(sys.stderr, message, avoid_logging=True)

    _, stderr = capsys.readouterr()
    assert stderr == expected


def test_secrets_copy(capsys, log_filepath):
    printer = Printer(log_filepath)

    secrets = ["banana", "watermelon"]

    message = "apple banana orange watermelon"
    expected = "apple ***** orange *****\n" * 2

    printer.set_secrets(secrets)
    printer.show(sys.stderr, message, avoid_logging=True)

    # Modify the client-side list to make sure it doesn't affect
    # the printer
    secrets.pop(0)
    printer.show(sys.stderr, message, avoid_logging=True)

    _, stderr = capsys.readouterr()
    assert stderr == expected


def test_secrets_log(log_filepath):
    printer = Printer(log_filepath)

    secrets = ["banana", "watermelon"]

    message = "apple banana orange watermelon"
    expected = "apple ***** orange *****\n"

    printer.set_secrets(secrets)
    printer.show(None, message, use_timestamp=False)

    # Chop off the timestamp
    obtained = log_filepath.read_text()
    start = obtained.find("apple")

    assert obtained[start:] == expected


def test_secrets_progress_bar(capsys, log_filepath, monkeypatch):
    stream = sys.stderr
    monkeypatch.setattr(stream, "isatty", lambda: True)
    printer = Printer(log_filepath)

    secrets = ["banana", "watermelon"]

    message = "apple banana orange watermelon"
    expected = "apple ***** orange *****"

    printer.set_secrets(secrets)
    printer.progress_bar(stream, message, progress=0.0, total=1.0, use_timestamp=False)

    _, stderr = capsys.readouterr()
    assert stderr.startswith(expected)


def test_secrets_terminal_prefix(capsys, log_filepath, monkeypatch):
    stream = sys.stderr
    monkeypatch.setattr(stream, "isatty", lambda: True)
    printer = Printer(log_filepath)

    message = "apple banana orange watermelon"

    # Set secrets first, then prefix
    printer.set_secrets(["watermelon"])
    printer.set_terminal_prefix("banana watermelon")
    printer.show(stream, message)

    # Set prefix first, then secrets
    printer.set_terminal_prefix("watermelon banana")
    printer.set_secrets(["banana"])
    printer.show(stream, message)

    expected = [
        "banana ***** :: apple banana orange *****",
        "watermelon ***** :: apple ***** orange watermelon",
    ]

    _, stderr = capsys.readouterr()
    obtained = [l.strip() for l in stderr.splitlines()]
    assert obtained == expected
