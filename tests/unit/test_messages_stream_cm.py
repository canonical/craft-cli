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
    scm = _StreamContextManager(recording_printer, "initial text", None)

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
    scm = _StreamContextManager(recording_printer, "initial text", stream)

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
    scm = _StreamContextManager(recording_printer, "initial text", None)

    with scm as context_manager:
        # the pipe reader is working
        assert scm.pipe_reader.is_alive()
        assert context_manager is scm.pipe_w

    # the pipe reader is stopped
    assert not scm.pipe_reader.is_alive()


def test_streamcm_dont_consume_exceptions(recording_printer):
    """It lets the exceptions go through."""
    with pytest.raises(ValueError):
        with _StreamContextManager(recording_printer, "initial text", None):
            raise ValueError()


# -- tests for the pipe reader


@pytest.mark.parametrize("stream", [sys.stdout, sys.stderr])
def test_pipereader_simple(recording_printer, stream):
    """Basic pipe reader usage."""
    pipe_r, pipe_w = os.pipe()
    prt = _PipeReaderThread(pipe_r, recording_printer, stream)
    prt.start()
    os.write(pipe_w, b"123\n")
    prt.stop()

    (msg,) = recording_printer.written_lines  # pylint: disable=unbalanced-tuple-unpacking
    assert msg.stream == stream
    assert msg.text == ":: 123"  # unicode, with the prefix, and without the newline
    assert msg.use_timestamp is True
    assert msg.end_line is True
    assert msg.ephemeral is False
    assert msg.bar_progress is None
    assert msg.bar_total is None


# escribir de a partecitas con un enter en el medio
def test_pipereader_chunk_assembler(recording_printer, monkeypatch):
    """Converts ok arbitrary chunks to lines."""
    monkeypatch.setattr(messages, "_PIPE_READER_CHUNK_SIZE", 5)
    pipe_r, pipe_w = os.pipe()
    prt = _PipeReaderThread(pipe_r, recording_printer, sys.stdout)
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
        os.write(pipe_w, chunk)
        time.sleep(0.001)

    prt.stop()

    msg1, msg2 = recording_printer.written_lines
    assert msg1.text == ":: ------abcde---"
    assert msg2.text == ":: otherline---"
