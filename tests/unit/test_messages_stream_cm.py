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

"""Tests that check the stream context manager and auxiliary class."""

import os
import sys
import threading
import time

import pytest

from craft_cli import messages
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


# -- tests for the stream context manager


def test_streamcm_init_silent(recording_printer):
    """Check the context manager bootstrapping with no stream."""
    scm = _StreamContextManager(
        recording_printer, "initial text", stream=None, use_timestamp=False
    )

    # no initial message
    assert not recording_printer.written_lines

    # check it used the pipe reader correctly
    assert isinstance(scm.pipe_reader, _PipeReaderThread)
    assert scm.pipe_reader.printer == recording_printer
    assert scm.pipe_reader.stream is None
    assert not scm.pipe_reader.is_alive()


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_streamcm_init_with_stream(recording_printer, stream):
    """Check the context manager bootstrapping with a stream."""
    scm = _StreamContextManager(
        recording_printer, "initial text", stream=stream, use_timestamp=False
    )

    # initial message
    (msg,) = recording_printer.written_lines  # pylint: disable=unbalanced-tuple-unpacking
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
        recording_printer, "initial text", stream=stream, use_timestamp=True
    )

    # initial message
    (msg,) = recording_printer.written_lines  # pylint: disable=unbalanced-tuple-unpacking
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


def test_streamcm_usage_lifecycle(recording_printer):
    """Enters and exits the context manager correctly."""
    scm = _StreamContextManager(
        recording_printer, "initial text", stream=None, use_timestamp=False
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
            recording_printer, "initial text", stream=None, use_timestamp=False
        ):
            raise ValueError()


# -- tests for the pipe reader


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_pipereader_simple(recording_printer, stream):
    """Basic pipe reader usage."""
    prt = _PipeReaderThread(recording_printer, stream, use_timestamp=False)
    prt.start()
    os.write(prt.write_pipe, b"123\n")
    prt.stop()

    (msg,) = recording_printer.written_lines  # pylint: disable=unbalanced-tuple-unpacking
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
    prt = _PipeReaderThread(recording_printer, stream, use_timestamp=True)
    prt.start()
    os.write(prt.write_pipe, b"123\n")
    prt.stop()

    (msg,) = recording_printer.written_lines  # pylint: disable=unbalanced-tuple-unpacking
    assert msg.stream == stream
    assert msg.text == ":: 123"  # unicode, with the prefix, and without the newline
    assert msg.use_timestamp is True
    assert msg.end_line is True
    assert msg.ephemeral is False
    assert msg.bar_progress is None
    assert msg.bar_total is None


def test_pipereader_chunk_assembler(recording_printer, monkeypatch):
    """Converts ok arbitrary chunks to lines."""
    monkeypatch.setattr(messages, "_PIPE_READER_CHUNK_SIZE", 5)
    prt = _PipeReaderThread(recording_printer, sys.stdout, use_timestamp=False)
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

    msg1, msg2 = recording_printer.written_lines
    assert msg1.text == ":: ------abcde---"
    assert msg2.text == ":: otherline---"
