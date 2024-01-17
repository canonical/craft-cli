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

"""Tests that check the stream context manager and auxiliary class."""

import os
import sys
import threading
import time

import pytest

from craft_cli import messages, printer
from craft_cli.messages import _PipeReaderThread, _StreamContextManager


@pytest.fixture(autouse=True)
def thread_guard(tmp_path):
    """Ensure that any started pipe reader is stopped after the test."""
    # let's run the test first
    yield

    # stop all spinner threads
    for thread in threading.enumerate():
        if isinstance(thread, _PipeReaderThread):
            thread.stop()


@pytest.fixture(autouse=True)
def force_terminal_behaviour(monkeypatch):
    """Fixture to force the "terminal" behaviour."""
    monkeypatch.setattr(printer, "_stream_is_terminal", lambda stream: True)


# -- tests for the stream context manager


def test_streamcm_init_silent(recording_printer):
    """Check the context manager bootstrapping with no stream."""
    scm = _StreamContextManager(
        recording_printer,
        "initial text",
        stream=None,
        use_timestamp=False,
        ephemeral_mode=False,
    )

    # no initial message
    assert not recording_printer.written_terminal_lines

    # check it used the pipe reader correctly
    assert isinstance(scm.pipe_reader, _PipeReaderThread)
    assert scm.pipe_reader.printer == recording_printer
    assert scm.pipe_reader.stream is None
    assert not scm.pipe_reader.is_alive()


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_streamcm_init_with_stream(recording_printer, stream):
    """Check the context manager bootstrapping with a stream."""
    scm = _StreamContextManager(
        recording_printer,
        "initial text",
        stream=stream,
        use_timestamp=False,
        ephemeral_mode=False,
    )

    # initial message
    (msg,) = recording_printer.written_terminal_lines
    assert msg.stream == stream
    assert msg.text == "initial text"
    assert msg.use_timestamp is False
    assert msg.end_line is True
    assert msg.ephemeral is False
    assert msg.bar_progress is None
    assert msg.bar_total is None

    # check it used the pipe reader correctly
    assert isinstance(scm.pipe_reader, _PipeReaderThread)
    assert scm.pipe_reader.printer == recording_printer
    assert scm.pipe_reader.stream == stream
    assert not scm.pipe_reader.is_alive()


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_streamcm_init_with_stream_and_timestamp(recording_printer, stream):
    """Check the context manager bootstrapping with a stream and a timestamp."""
    scm = _StreamContextManager(
        recording_printer,
        "initial text",
        stream=stream,
        use_timestamp=True,
        ephemeral_mode=False,
    )

    # initial message
    (msg,) = recording_printer.written_terminal_lines
    assert msg.stream == stream
    assert msg.text == "initial text"
    assert msg.use_timestamp is True
    assert msg.end_line is True
    assert msg.ephemeral is False
    assert msg.bar_progress is None
    assert msg.bar_total is None

    # check it used the pipe reader correctly
    assert isinstance(scm.pipe_reader, _PipeReaderThread)
    assert scm.pipe_reader.printer == recording_printer
    assert scm.pipe_reader.stream == stream
    assert not scm.pipe_reader.is_alive()


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_streamcm_init_with_stream_ephemeral(recording_printer, stream):
    """Check the context manager bootstrapping with a stream in ephemeral mode."""
    scm = _StreamContextManager(
        recording_printer,
        "initial text",
        stream=stream,
        use_timestamp=False,
        ephemeral_mode=True,
    )

    # initial message
    (msg,) = recording_printer.written_terminal_lines
    assert msg.stream == stream
    assert msg.text == "initial text"
    assert msg.use_timestamp is False
    assert msg.end_line is False
    assert msg.ephemeral is True
    assert msg.bar_progress is None
    assert msg.bar_total is None

    # check it used the pipe reader correctly
    assert isinstance(scm.pipe_reader, _PipeReaderThread)
    assert scm.pipe_reader.printer == recording_printer
    assert scm.pipe_reader.stream == stream
    assert not scm.pipe_reader.is_alive()


def test_streamcm_usage_lifecycle(recording_printer):
    """Enters and exits the context manager correctly."""
    scm = _StreamContextManager(
        recording_printer,
        "initial text",
        stream=None,
        use_timestamp=False,
        ephemeral_mode=False,
    )

    with scm as context_manager:
        # the pipe reader is working
        assert scm.pipe_reader.is_alive()
        assert context_manager is scm.pipe_reader.write_pipe

    # the pipe reader is stopped
    assert not scm.pipe_reader.is_alive()


def test_streamcm_dont_consume_exceptions(recording_printer):
    """It lets the exceptions go through."""
    with pytest.raises(ValueError):
        with _StreamContextManager(
            recording_printer,
            "initial text",
            stream=None,
            use_timestamp=False,
            ephemeral_mode=False,
        ):
            raise ValueError()


# -- tests for the pipe reader


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_pipereader_simple(recording_printer, stream):
    """Basic pipe reader usage."""
    flags = {"use_timestamp": False, "ephemeral": False, "end_line": True}
    prt = _PipeReaderThread(recording_printer, stream, flags)
    prt.start()
    os.write(prt.write_pipe, b"123\n")
    prt.stop()

    (msg,) = recording_printer.written_terminal_lines
    assert msg.stream == stream
    assert msg.text == ":: 123"  # unicode, with the prefix, and without the newline
    assert msg.use_timestamp is False
    assert msg.end_line is True
    assert msg.ephemeral is False
    assert msg.bar_progress is None
    assert msg.bar_total is None


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_pipereader_with_timestamp(recording_printer, stream):
    """Basic pipe reader usage with a timestamp."""
    flags = {"use_timestamp": True, "ephemeral": False, "end_line": True}
    prt = _PipeReaderThread(recording_printer, stream, flags)
    prt.start()
    os.write(prt.write_pipe, b"123\n")
    prt.stop()

    (msg,) = recording_printer.written_terminal_lines
    assert msg.stream == stream
    assert msg.text == ":: 123"  # unicode, with the prefix, and without the newline
    assert msg.use_timestamp is True
    assert msg.end_line is True
    assert msg.ephemeral is False
    assert msg.bar_progress is None
    assert msg.bar_total is None


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_pipereader_ephemeral(recording_printer, stream):
    """Basic pipe reader usage in ephemeral moede."""
    flags = {"use_timestamp": False, "ephemeral": True, "end_line": False}
    prt = _PipeReaderThread(recording_printer, stream, flags)
    prt.start()
    os.write(prt.write_pipe, b"123\n")
    prt.stop()

    (msg,) = recording_printer.written_terminal_lines
    assert msg.stream == stream
    assert msg.text == ":: 123"  # unicode, with the prefix, and without the newline
    assert msg.use_timestamp is False
    assert msg.end_line is False
    assert msg.ephemeral is True
    assert msg.bar_progress is None
    assert msg.bar_total is None


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_pipereader_tabs(recording_printer, stream):
    """Check that tabs are converted to spaces."""
    flags = {"use_timestamp": False, "ephemeral": False, "end_line": True}
    prt = _PipeReaderThread(recording_printer, stream, flags)
    prt.start()
    os.write(prt.write_pipe, b"\t123\t456\n")
    prt.stop()

    (msg,) = recording_printer.written_terminal_lines
    assert msg.text == "::   123  456"  # tabs expanded into 2 spaces


@pytest.mark.parametrize(
    ("invalid_text", "expected"),
    [(b"\xf0\x28\x8c\xbc", "�(��"), (b"\xf0\x90\x28\xbc", "�(�"), (b"\xf0\x90\x8c\x28", "�(")],
)
def test_pipereader_invalid_utf8(recording_printer, invalid_text, expected):
    """Check that bytes that aren't valid utf-8 text don't crash."""
    invalid_bytes = b"valid prefix " + invalid_text + b" valid suffix\n"

    flags = {"use_timestamp": False, "ephemeral": False, "end_line": True}
    prt = _PipeReaderThread(recording_printer, sys.stdout, flags)
    prt.start()
    os.write(prt.write_pipe, invalid_bytes)
    prt.stop()

    (msg,) = recording_printer.written_terminal_lines
    assert msg.text == f":: valid prefix {expected} valid suffix"


def test_pipereader_chunk_assembler(recording_printer, monkeypatch):
    """Converts ok arbitrary chunks to lines."""
    monkeypatch.setattr(messages, "_PIPE_READER_CHUNK_SIZE", 5)
    flags = {"use_timestamp": False, "ephemeral": False, "end_line": True}
    prt = _PipeReaderThread(recording_printer, sys.stdout, flags)
    prt.start()

    # write different chunks, sleeping in the middle not for timing, but to let the
    # reading thread to work
    chunks = [
        b"------a",  # longer than the chunk size
        b"b",  # some small ones
        b"c",
        b"d",
        b"e",
        b"---\notherline",  # with an enter in the middle
        b"---\n",  # closing
    ]
    for chunk in chunks:
        os.write(prt.write_pipe, chunk)
        time.sleep(0.001)

    prt.stop()

    msg1, msg2 = recording_printer.written_terminal_lines
    assert msg1.text == ":: ------abcde---"
    assert msg2.text == ":: otherline---"


def test_no_fail_if_big_number_is_used(recording_printer):
    """Ensures that opening and closing a big number of objects doesn't fail."""
    flags = {"use_timestamp": False, "ephemeral": False, "end_line": True}
    # The limit is 1024 both in Linux and BSD, but each object opens two FDs
    for _ in range(514):
        prt = _PipeReaderThread(recording_printer, sys.stdout, flags)
        prt.start()
        prt.stop()

    assert True


def test_ensure_pipes_are_closed(recording_printer):
    """Ensures that all the resources are freed on exit."""
    flags = {"use_timestamp": False, "ephemeral": False, "end_line": True}
    prt = _PipeReaderThread(recording_printer, sys.stdout, flags)
    prt.start()
    prt.stop()
    with pytest.raises(OSError) as err:
        os.fstat(prt.read_pipe)
    assert err.value.errno == 9
    with pytest.raises(OSError) as err:
        os.fstat(prt.write_pipe)
    assert err.value.errno == 9
