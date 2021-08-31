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

# -- simple helpers


def test_terminal_width():
    """Check the terminal width helper."""
    assert messages.get_terminal_width() == shutil.get_terminal_size().columns


# -- tests for the writing line function


def test_writeline_simple_complete(capsys, monkeypatch):
    """Complete verification of _write_line for a simple case."""
    monkeypatch.setattr(messages, "get_terminal_width", lambda: 40)
    printer = _Printer()

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line(msg)
    assert printer.unfinished_stream == sys.stdout

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert out == test_text + " " * (39 - len(test_text))


def test_writeline_different_stream(capsys, monkeypatch):
    """Use a different stream."""
    monkeypatch.setattr(messages, "get_terminal_width", lambda: 40)
    printer = _Printer()

    test_text = "test text"
    msg = _MessageInfo(sys.stderr, test_text)
    printer._write_line(msg)
    assert printer.unfinished_stream == sys.stderr

    out, err = capsys.readouterr()
    assert not out

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    assert err == test_text + " " * (39 - len(test_text))


def test_writeline_with_timestamp(capsys, monkeypatch):
    """A timestamp was indicated to use."""
    monkeypatch.setattr(messages, "get_terminal_width", lambda: 40)
    printer = _Printer()

    fake_now = datetime(2009, 9, 1, 12, 13, 15, 123456)
    msg = _MessageInfo(sys.stdout, "test text", use_timestamp=True, created_at=fake_now)
    printer._write_line(msg)

    out, _ = capsys.readouterr()

    # output completes the terminal width (leaving space for the cursor), and
    # without a finishing newline
    expected_text = "2009-09-01 12:13:15.123 test text"
    assert out == expected_text + " " * (39 - len(expected_text))


def test_writeline_having_previous_message_out(capsys, monkeypatch):
    """There is a previous message to be completed (in stdout)."""
    monkeypatch.setattr(messages, "get_terminal_width", lambda: 40)
    printer = _Printer()
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text")

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line(msg)

    # stdout has the expected text but with an extra newline before
    out, err = capsys.readouterr()
    assert out == "\n" + test_text + " " * (39 - len(test_text))
    assert not err


def test_writeline_having_previous_message_err(capsys, monkeypatch):
    """There is a previous message to be completed (in stderr)."""
    monkeypatch.setattr(messages, "get_terminal_width", lambda: 40)
    printer = _Printer()
    printer.prv_msg = _MessageInfo(sys.stderr, "previous text")

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line(msg)

    # stdout just has the expected text, and an extra newline was sent to stderr
    out, err = capsys.readouterr()
    assert out == test_text + " " * (39 - len(test_text))
    assert err == "\n"


def test_writeline_having_previous_message_complete(capsys, monkeypatch):
    """There is a previous message which is already complete."""
    monkeypatch.setattr(messages, "get_terminal_width", lambda: 40)
    printer = _Printer()
    printer.prv_msg = _MessageInfo(sys.stdout, "previous text", end_line=True)

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text)
    printer._write_line(msg)

    # stdout has the expected text without anything extra
    out, err = capsys.readouterr()
    assert out == test_text + " " * (39 - len(test_text))
    assert not err


def test_writeline_indicated_to_complete(capsys, monkeypatch):
    """The message is indicated to complete the line."""
    monkeypatch.setattr(messages, "get_terminal_width", lambda: 40)
    printer = _Printer()

    test_text = "test text"
    msg = _MessageInfo(sys.stdout, test_text, end_line=True)
    printer._write_line(msg)

    out, err = capsys.readouterr()
    assert not err

    # output completes the terminal width (leaving space for the cursor), and
    # WITH a finishing newline
    assert out == test_text + " " * (39 - len(test_text)) + "\n"


# -- tests for message showing external API


class RecordingPrinter(_Printer):
    """A Printer isolated from outputs.

    Instead, it records all messages to print.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.written_lines = []

    def _write_line(self, message):
        """Overwrite the real one to avoid it and record the message."""
        self.written_lines.append(message)


@pytest.mark.parametrize("stream", [None, sys.stdout, sys.stderr])
def test_show_defaults(stream):
    """Write a message with all defaults (for the different valid streams)."""
    before = datetime.now()
    printer = RecordingPrinter()
    printer.show(stream, "test text")

    # check message written
    (msg,) = printer.written_lines  # pylint: disable=unbalanced-tuple-unpacking
    assert msg.stream == stream
    assert msg.text == "test text"
    assert msg.use_timestamp is False
    assert msg.end_line is False
    assert before <= msg.created_at <= datetime.now()

    # check it was properly stored for the future
    assert printer.prv_msg is msg  # verify it's the same, not that it was rebuilt, for timestamp


def test_show_use_timestamp():
    """Control on message's use_timestamp flag."""
    printer = RecordingPrinter()
    printer.show(sys.stdout, "test text", use_timestamp=True)
    (msg,) = printer.written_lines  # pylint: disable=unbalanced-tuple-unpacking
    assert msg.use_timestamp is True


def test_show_end_line():
    """Control on message's end_line flag."""
    printer = RecordingPrinter()
    printer.show(sys.stdout, "test text", end_line=True)
    (msg,) = printer.written_lines  # pylint: disable=unbalanced-tuple-unpacking
    assert msg.end_line is True


# -- tests for stopping the printer


def test_stop_streams_ok(capsys):
    """Stopping when all streams complete."""
    printer = _Printer()
    assert printer.unfinished_stream is None
    printer.stop()

    out, err = capsys.readouterr()
    assert not out
    assert not err


def test_stop_streams_unfinished_out(capsys):
    """Stopping when stdout is not complete."""
    printer = _Printer()
    printer.unfinished_stream = sys.stdout
    printer.stop()

    out, err = capsys.readouterr()
    assert out == "\n"
    assert not err


def test_stop_streams_unfinished_err(capsys):
    """Stopping when stderr is not complete."""
    printer = _Printer()
    printer.unfinished_stream = sys.stderr
    printer.stop()

    out, err = capsys.readouterr()
    assert not out
    assert err == "\n"
