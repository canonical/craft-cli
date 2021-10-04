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

"""Tests that check the whole Emitter machinery."""

import sys
from unittest.mock import call, patch

import pytest

from craft_cli import messages
from craft_cli.messages import Emitter, EmitterMode


class RecordingEmitter(Emitter):
    """Class to cheat pyright.

    Otherwise it complains I'm setting printer_class to Emitter.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.printer_calls = []


@pytest.fixture
def get_initiated_emitter(tmp_path, monkeypatch):
    """Provide an initiated Emitter ready to test.

    It has a patched "printer" and an easy way to test its calls (after it was initiated).

    It's used almost in all tests (except those that test the init call).
    """
    fake_logpath = str(tmp_path / "fakelog.log")
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: fake_logpath)
    with patch("craft_cli.messages._Printer", autospec=True) as mock_printer:

        def func(mode, greeting="default greeting"):
            emitter = RecordingEmitter()
            emitter.init(mode, "testappname", greeting)
            emitter.printer_calls = mock_printer.mock_calls
            emitter.printer_calls.clear()
            return emitter

        yield func


# -- tests for init and setting mode


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_init_quietish(mode, tmp_path, monkeypatch):
    """Init the class in some quiet-ish mode."""
    # avoid using a real log file
    fake_logpath = str(tmp_path / "fakelog.log")
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: fake_logpath)

    greeting = "greeting"
    emitter = Emitter()
    with patch("craft_cli.messages._Printer") as mock_printer:
        emitter.init(mode, "testappname", greeting)

    assert emitter._mode == mode
    assert mock_printer.mock_calls == [
        call(fake_logpath),  # the _Printer instantiation, passing the log filepath
        call().show(None, "greeting"),  # the greeting, only sent to the log
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_init_verboseish(mode, tmp_path, monkeypatch):
    """Init the class in some verbose-ish mode."""
    # avoid using a real log file
    fake_logpath = str(tmp_path / "fakelog.log")
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: fake_logpath)

    greeting = "greeting"
    emitter = Emitter()
    with patch("craft_cli.messages._Printer") as mock_printer:
        emitter.init(mode, "testappname", greeting)

    assert emitter._mode == mode
    log_locat = f"Logging execution to '{fake_logpath}'"
    assert mock_printer.mock_calls == [
        call(fake_logpath),  # the _Printer instantiation, passing the log filepath
        call().show(None, "greeting"),  # the greeting, only sent to the log
        call().show(sys.stderr, greeting, use_timestamp=True, end_line=True, avoid_logging=True),
        call().show(sys.stderr, log_locat, use_timestamp=True, end_line=True, avoid_logging=True),
    ]


@pytest.mark.parametrize("method_name", [x for x in dir(Emitter) if x[0] != "_" and x != "init"])
def test_needs_init(method_name):
    """Check that calling other methods needs emitter first to be initiated."""
    emitter = Emitter()
    method = getattr(emitter, method_name)
    with pytest.raises(RuntimeError, match="Emitter needs to be initiated first"):
        method()


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_set_mode_quietish(get_initiated_emitter, mode):
    """Set the class to some quiet-ish mode."""
    greeting = "greeting"
    emitter = get_initiated_emitter(EmitterMode.QUIET, greeting=greeting)
    emitter.set_mode(mode)

    assert emitter._mode == mode
    assert emitter.printer_calls == []


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_set_mode_verboseish(get_initiated_emitter, mode):
    """Set the class to some verbose-ish mode."""
    greeting = "greeting"
    emitter = get_initiated_emitter(EmitterMode.QUIET, greeting=greeting)
    emitter.set_mode(mode)

    assert emitter._mode == mode
    log_locat = f"Logging execution to '{emitter._log_filepath}'"
    assert emitter.printer_calls == [
        call().show(sys.stderr, greeting, use_timestamp=True, avoid_logging=True, end_line=True),
        call().show(sys.stderr, log_locat, use_timestamp=True, avoid_logging=True, end_line=True),
    ]


# -- tests for emitting messages of all kind


@pytest.mark.parametrize("mode", EmitterMode)  # all modes!
def test_message_final(get_initiated_emitter, mode):
    """Emit a final message."""
    emitter = get_initiated_emitter(mode)
    emitter.message("some text")

    assert emitter.printer_calls == [
        call().show(sys.stdout, "some text", use_timestamp=False),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_message_intermediate_quietish(get_initiated_emitter, mode):
    """Emit an intermediate message when in a quiet-ish mode."""
    emitter = get_initiated_emitter(mode)
    emitter.message("some text", intermediate=True)

    assert emitter.printer_calls == [
        call().show(sys.stdout, "some text", use_timestamp=False),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_message_intermediate_verboseish(get_initiated_emitter, mode):
    """Emit an intermediate message when in a verbose-ish mode."""
    emitter = get_initiated_emitter(mode)
    emitter.message("some text", intermediate=True)

    assert emitter.printer_calls == [
        call().show(sys.stdout, "some text", use_timestamp=True),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
        EmitterMode.VERBOSE,
    ],
)
def test_trace_in_non_trace_modes(get_initiated_emitter, mode):
    """Only log the message."""
    emitter = get_initiated_emitter(mode)
    emitter.trace("some text")

    assert emitter.printer_calls == [
        call().show(None, "some text", use_timestamp=True),
    ]


def test_trace_in_trace_mode(get_initiated_emitter):
    """Log the message and show it in stderr."""
    emitter = get_initiated_emitter(EmitterMode.TRACE)
    emitter.trace("some text")

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=True),
    ]


def test_progress_in_quiet_mode(get_initiated_emitter):
    """Only log the message."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    emitter.progress("some text")

    assert emitter.printer_calls == [
        call().show(None, "some text", use_timestamp=False, ephemeral=True),
    ]


def test_progress_in_normal_mode(get_initiated_emitter):
    """Send to stderr (ephermeral) and log it."""
    emitter = get_initiated_emitter(EmitterMode.NORMAL)
    emitter.progress("some text")

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=False, ephemeral=True),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_progress_in_verboseish_modes(get_initiated_emitter, mode):
    """Send to stderr (permanent, with timestamp) and log it."""
    emitter = get_initiated_emitter(mode)
    emitter.progress("some text")

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=True, ephemeral=False),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.NORMAL,
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_progressbar_in_useful_modes(get_initiated_emitter, mode):
    """Show the initial message to stderr and init _Progresser correctly."""
    emitter = get_initiated_emitter(mode)
    progresser = emitter.progress_bar("some text", 5000)

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", ephemeral=True),
    ]
    assert progresser.total == 5000
    assert progresser.text == "some text"
    assert progresser.stream == sys.stderr
    assert progresser.delta is True


def test_progressbar_with_delta_false(get_initiated_emitter):
    """Init _Progresser with delta=False."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    progresser = emitter.progress_bar("some text", 5000, delta=False)
    assert progresser.delta is False


def test_progressbar_in_quiet_mode(get_initiated_emitter):
    """Do not show the initial message (but log it) and init _Progresser with stream in None."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    progresser = emitter.progress_bar("some text", 5000)

    assert emitter.printer_calls == [
        call().show(None, "some text", ephemeral=True),
    ]
    assert progresser.stream is None


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_openstream_in_quietish_modes(get_initiated_emitter, mode):
    """Return a stream context manager with the output stream in None."""
    emitter = get_initiated_emitter(mode)

    with patch("craft_cli.messages._StreamContextManager") as stream_context_manager_mock:
        instantiated_cm = object()
        stream_context_manager_mock.return_value = instantiated_cm
        context_manager = emitter.open_stream("some text")

    assert emitter.printer_calls == []
    assert context_manager is instantiated_cm
    assert stream_context_manager_mock.mock_calls == [
        call(emitter._printer, "some text", None),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_openstream_in_verboseish_modes(get_initiated_emitter, mode):
    """Return a stream context manager with stderr as the output stream."""
    emitter = get_initiated_emitter(mode)

    with patch("craft_cli.messages._StreamContextManager") as stream_context_manager_mock:
        instantiated_cm = object()
        stream_context_manager_mock.return_value = instantiated_cm
        context_manager = emitter.open_stream("some text")

    assert emitter.printer_calls == []
    assert context_manager is instantiated_cm
    assert stream_context_manager_mock.mock_calls == [
        call(emitter._printer, "some text", sys.stderr),
    ]


# -- tests for stopping the machinery


def test_ended_ok(get_initiated_emitter):
    """Finish everything."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    emitter.ended_ok()

    assert emitter.printer_calls == [call().stop()]
