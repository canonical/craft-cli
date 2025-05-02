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

"""Tests that check the whole Emitter machinery."""

import logging
import sys
from unittest import mock
from unittest.mock import call, patch
from typing import Any, cast, Callable

import pytest
import pytest_mock

from craft_cli import messages
from craft_cli.errors import CraftError, CraftCommandError
from craft_cli.messages import Emitter, EmitterMode, _Handler

FAKE_LOG_NAME = "fakelog.log"


@pytest.fixture(autouse=True)
def init_emitter():
    """Disable the automatic init emitter fixture for this entire module."""


@pytest.fixture(autouse=True)
def clean_logging_handler():
    """Remove the used handler to properly isolate tests."""
    logger = logging.getLogger("")
    to_remove = [x for x in logger.handlers if isinstance(x, _Handler)]
    for handler in to_remove:
        logger.removeHandler(handler)

@pytest.fixture
def mock_isatty(mocker):
    return mocker.patch("sys.stdin.isatty", return_value=True)


@pytest.fixture
def mock_input(mocker):
    return mocker.patch("builtins.input", return_value="")


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
    fake_logpath = str(tmp_path / FAKE_LOG_NAME)
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: fake_logpath)
    with patch("craft_cli.messages.Printer", autospec=True) as mock_printer:

        def func(mode, *, greeting="default greeting", **kwargs):
            emitter = RecordingEmitter()
            emitter.init(mode, "testappname", greeting, **kwargs)
            emitter.printer_calls = mock_printer.mock_calls
            emitter.printer_calls.clear()
            return emitter

        yield func

def emitter_methods(init: bool, stop: bool = True, exclude: list[str] = []) -> list[Callable[..., Any]]:
    """Provide a list of all public methods on an Emitter object.

    :param init: Whether or not to initialize the emitter first
    :param stop: Whether or not to stop the emitter after initialization. Does nothing if init is False.
        Defaults to true.
    :param exclude: A list of method names to exclude from the final output. Defaults to empty.
    """
    emitter = Emitter()
    if init:
        emitter.init(EmitterMode.QUIET, "testappname", "default greeting")
        if stop:
            emitter.ended_ok()

    # Collect all the public methods in Emitter
    all_methods = [item for item in dir(Emitter) if item[0] != "_"]

    # Filter out from the exclusion list
    all_methods = [item for item in all_methods if item not in exclude]

    # Get the actual attributes
    all_methods = [getattr(emitter, item) for item in all_methods]

    # Filter out anything that isn't actually a method
    all_methods = [item for item in all_methods if isinstance(item, Callable)]

    return all_methods


# -- tests for init and setting/getting mode


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.BRIEF,
    ],
)
def test_init_quietish(mode, tmp_path, monkeypatch):
    """Init the class in some quiet-ish mode."""
    # avoid using a real log file
    fake_logpath = str(tmp_path / FAKE_LOG_NAME)
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: fake_logpath)

    greeting = "greeting"
    emitter = Emitter()
    with patch("craft_cli.messages.Printer") as mock_printer:
        emitter.init(mode, "testappname", greeting)

    assert emitter._mode == mode
    assert mock_printer.mock_calls == [
        call(fake_logpath),  # the Printer instantiation, passing the log filepath
        call().show(None, "greeting"),  # the greeting, only sent to the log
    ]

    # log handler is properly setup
    logger = logging.getLogger("")
    (handler,) = [x for x in logger.handlers if isinstance(x, _Handler)]
    assert handler.mode == mode


def test_init_verbose_mode(tmp_path, monkeypatch):
    """Init the class in verbose mode."""
    # avoid using a real log file
    fake_logpath = str(tmp_path / FAKE_LOG_NAME)
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: fake_logpath)

    greeting = "greeting"
    emitter = Emitter()
    with patch("craft_cli.messages.Printer") as mock_printer:
        emitter.init(EmitterMode.VERBOSE, "testappname", greeting)

    assert emitter._mode == EmitterMode.VERBOSE
    log_locat = f"Logging execution to {fake_logpath!r}"
    assert mock_printer.mock_calls == [
        call(fake_logpath),  # the Printer instantiation, passing the log filepath
        call().show(None, "greeting"),  # the greeting, only sent to the log
        call().show(sys.stderr, greeting, use_timestamp=False, end_line=True, avoid_logging=True),
        call().show(sys.stderr, log_locat, use_timestamp=False, end_line=True, avoid_logging=True),
    ]

    # log handler is properly setup
    logger = logging.getLogger("")
    (handler,) = [x for x in logger.handlers if isinstance(x, _Handler)]
    assert handler.mode == EmitterMode.VERBOSE


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
def test_init_developer_modes(mode, tmp_path, monkeypatch):
    """Init the class in developer modes."""
    # avoid using a real log file
    fake_logpath = str(tmp_path / FAKE_LOG_NAME)
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: fake_logpath)

    greeting = "greeting"
    emitter = Emitter()
    with patch("craft_cli.messages.Printer") as mock_printer:
        emitter.init(mode, "testappname", greeting)

    assert emitter._mode == mode
    log_locat = f"Logging execution to {fake_logpath!r}"
    assert mock_printer.mock_calls == [
        call(fake_logpath),  # the Printer instantiation, passing the log filepath
        call().show(None, "greeting"),  # the greeting, only sent to the log
        call().show(sys.stderr, greeting, use_timestamp=True, end_line=True, avoid_logging=True),
        call().show(sys.stderr, log_locat, use_timestamp=True, end_line=True, avoid_logging=True),
    ]

    # log handler is properly setup
    logger = logging.getLogger("")
    (handler,) = [x for x in logger.handlers if isinstance(x, _Handler)]
    assert handler.mode == mode

@pytest.mark.parametrize("method", emitter_methods(init=False, exclude=["init"]))
def test_needs_init(method):
    """Check that calling other methods needs emitter first to be initiated."""
    with pytest.raises(RuntimeError, match="Emitter needs to be initiated first"):
        method()


def test_init_receiving_logfile(tmp_path, monkeypatch):
    """Init the class in some verbose-ish mode."""
    # ensure it's not using the standard log filepath provider (that pollutes user dirs)
    monkeypatch.setattr(messages, "_get_log_filepath", None)

    greeting = "greeting"
    emitter = Emitter()
    fake_logpath = tmp_path / FAKE_LOG_NAME
    with patch("craft_cli.messages.Printer") as mock_printer:
        emitter.init(EmitterMode.DEBUG, "testappname", greeting, log_filepath=fake_logpath)

    # filepath is properly informed and passed to the printer
    log_locat = f"Logging execution to {str(fake_logpath)!r}"
    assert mock_printer.mock_calls == [
        call(fake_logpath),  # the Printer instantiation, passing the log filepath
        call().show(None, "greeting"),  # the greeting, only sent to the log
        call().show(sys.stderr, greeting, use_timestamp=True, end_line=True, avoid_logging=True),
        call().show(sys.stderr, log_locat, use_timestamp=True, end_line=True, avoid_logging=True),
    ]


def test_init_double_regular_mode(tmp_path, monkeypatch):
    """Double init in regular usage mode."""
    # ensure it's not using the standard log filepath provider (that pollutes user dirs)
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: tmp_path / FAKE_LOG_NAME)

    emitter = Emitter()

    with patch("craft_cli.messages.Printer"):
        emitter.init(EmitterMode.VERBOSE, "testappname", "greeting")

        with pytest.raises(RuntimeError, match="Double Emitter init detected!"):
            emitter.init(EmitterMode.VERBOSE, "testappname", "greeting")


def test_init_double_tests_mode(tmp_path, monkeypatch):
    """Double init in tests usage mode."""
    # ensure it's not using the standard log filepath provider (that pollutes user dirs)
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: tmp_path / FAKE_LOG_NAME)

    monkeypatch.setattr(messages, "TESTMODE", True)
    emitter = Emitter()

    with patch("craft_cli.messages.Printer"):
        with patch.object(emitter, "_stop") as mock_stop:
            emitter.init(EmitterMode.VERBOSE, "testappname", "greeting")
            assert mock_stop.called is False
            emitter.init(EmitterMode.VERBOSE, "testappname", "greeting")
            assert mock_stop.called is True


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.BRIEF,
    ],
)
def test_set_mode_quietish(get_initiated_emitter, mode):
    """Set the class to some quiet-ish mode."""
    greeting = "greeting"
    emitter = get_initiated_emitter(EmitterMode.QUIET, greeting=greeting)
    emitter.set_mode(mode)

    assert emitter._mode == mode
    assert emitter.get_mode() == mode
    assert emitter.printer_calls == []

    # log handler is affected
    logger = logging.getLogger("")
    (handler,) = [x for x in logger.handlers if isinstance(x, _Handler)]
    assert handler.mode == mode


def test_set_mode_verbose_mode(get_initiated_emitter):
    """Set the class to verbose mode."""
    greeting = "greeting"
    emitter = get_initiated_emitter(EmitterMode.QUIET, greeting=greeting)
    emitter.set_mode(EmitterMode.VERBOSE)

    assert emitter._mode == EmitterMode.VERBOSE
    assert emitter.get_mode() == EmitterMode.VERBOSE
    log_locat = f"Logging execution to {emitter._log_filepath!r}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, greeting, use_timestamp=False, avoid_logging=True, end_line=True),
        call().show(sys.stderr, log_locat, use_timestamp=False, avoid_logging=True, end_line=True),
    ]

    # log handler is affected
    logger = logging.getLogger("")
    (handler,) = [x for x in logger.handlers if isinstance(x, _Handler)]
    assert handler.mode == EmitterMode.VERBOSE


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
def test_set_mode_developer_modes(get_initiated_emitter, mode):
    """Set the class to developer modes."""
    greeting = "greeting"
    emitter = get_initiated_emitter(EmitterMode.QUIET, greeting=greeting)
    emitter.set_mode(mode)

    assert emitter._mode == mode
    assert emitter.get_mode() == mode
    log_locat = f"Logging execution to {emitter._log_filepath!r}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, greeting, use_timestamp=True, avoid_logging=True, end_line=True),
        call().show(sys.stderr, log_locat, use_timestamp=True, avoid_logging=True, end_line=True),
    ]

    # log handler is affected
    logger = logging.getLogger("")
    (handler,) = [x for x in logger.handlers if isinstance(x, _Handler)]
    assert handler.mode == mode


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
def test_set_mode_repeated(get_initiated_emitter, mode):
    """Repeatedly setting the same mode should not emit multiple greetings."""
    greeting = "greeting"
    emitter = get_initiated_emitter(EmitterMode.QUIET, greeting=greeting)

    emitter.set_mode(mode)
    emitter.set_mode(mode)

    log_locat = f"Logging execution to {emitter._log_filepath!r}"
    extra_print_args = {"use_timestamp": mock.ANY, "avoid_logging": True, "end_line": True}

    # Only a single printing of the greeting and the logpath
    assert emitter.printer_calls == [
        call().show(sys.stderr, greeting, **extra_print_args),
        call().show(sys.stderr, log_locat, **extra_print_args),
    ]


# -- tests for emitting messages of all kind


def test_message_final_quiet(get_initiated_emitter):
    """Emit a final message."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    emitter.message("some text")

    assert emitter.printer_calls == [
        call().show(None, "some text"),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.BRIEF,
        EmitterMode.VERBOSE,
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
def test_message_final_not_quiet(get_initiated_emitter, mode):
    """Emit a final message."""
    emitter = get_initiated_emitter(mode)
    emitter.message("some text")

    assert emitter.printer_calls == [
        call().show(sys.stdout, "some text"),
    ]


def test_progress_in_quiet_mode(get_initiated_emitter):
    """Only log the message."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    emitter.progress("some text")

    assert emitter.printer_calls == [
        call().show(None, "some text", use_timestamp=False, ephemeral=True),
    ]


def test_progress_in_brief_mode(get_initiated_emitter):
    """Send to stderr (ephermeral) and log it."""
    emitter = get_initiated_emitter(EmitterMode.BRIEF)
    emitter.progress("some text")

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=False, ephemeral=True),
    ]


def test_progress_in_verbose_mode(get_initiated_emitter):
    """Send to stderr (ephermeral) and log it."""
    emitter = get_initiated_emitter(EmitterMode.VERBOSE)
    emitter.progress("some text")

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=False, ephemeral=False),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
def test_progress_in_developer_modes(get_initiated_emitter, mode):
    """Send to stderr (permanent, with timestamp) and log it."""
    emitter = get_initiated_emitter(mode)
    emitter.progress("some text")

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=True, ephemeral=False),
    ]


def test_progress_permanent_in_quiet_mode(get_initiated_emitter):
    """Only log the message."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    emitter.progress("some text", permanent=True)

    assert emitter.printer_calls == [
        call().show(None, "some text", use_timestamp=False, ephemeral=True),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.BRIEF,
        EmitterMode.VERBOSE,
    ],
)
def test_progress_permanent_in_brief_verbose_modes(get_initiated_emitter, mode):
    """Send to stderr (ephermeral) and log it."""
    emitter = get_initiated_emitter(mode)
    emitter.progress("some text", permanent=True)

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=False, ephemeral=False),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
def test_progress_permanent_in_developer_modes(get_initiated_emitter, mode):
    """Send to stderr (permanent, with timestamp) and log it."""
    emitter = get_initiated_emitter(mode)
    emitter.progress("some text", permanent=True)

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=True, ephemeral=False),
    ]


def test_progressbar_in_quiet_mode(get_initiated_emitter):
    """Set up and return the progress bar progresser properly."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    progresser = emitter.progress_bar("some text", 5000)

    assert emitter.printer_calls == []
    assert progresser.total == 5000
    assert progresser.text == "some text"
    assert progresser.stream is None
    assert progresser.use_timestamp is False
    assert progresser.ephemeral_context is True


def test_progressbar_in_brief_mode(get_initiated_emitter):
    """Set up and return the progress bar progresser properly."""
    emitter = get_initiated_emitter(EmitterMode.BRIEF)
    progresser = emitter.progress_bar("some text", 5000)

    assert emitter.printer_calls == []
    assert progresser.total == 5000
    assert progresser.text == "some text"
    assert progresser.stream == sys.stderr
    assert progresser.delta is True
    assert progresser.use_timestamp is False
    assert progresser.ephemeral_context is True


def test_progressbar_in_verbose_mode(get_initiated_emitter):
    """Set up and return the progress bar progresser properly."""
    emitter = get_initiated_emitter(EmitterMode.VERBOSE)
    progresser = emitter.progress_bar("some text", 5000)

    assert emitter.printer_calls == []
    assert progresser.total == 5000
    assert progresser.text == "some text"
    assert progresser.stream == sys.stderr
    assert progresser.delta is True
    assert progresser.use_timestamp is False
    assert progresser.ephemeral_context is False


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
def test_progressbar_in_developer_modes(get_initiated_emitter, mode):
    """Set up and return the progress bar progresser properly."""
    emitter = get_initiated_emitter(mode)
    progresser = emitter.progress_bar("some text", 5000)

    assert emitter.printer_calls == []
    assert progresser.total == 5000
    assert progresser.text == "some text"
    assert progresser.stream == sys.stderr
    assert progresser.delta is True
    assert progresser.use_timestamp is True
    assert progresser.ephemeral_context is False


def test_progressbar_with_delta_false(get_initiated_emitter):
    """Init _Progresser with delta=False."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    progresser = emitter.progress_bar("some text", 5000, delta=False)
    assert progresser.delta is False


def test_openstream_in_quiet_mode(get_initiated_emitter):
    """Return a stream context manager with the output stream in None."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)

    with patch("craft_cli.messages._StreamContextManager") as stream_context_manager_mock:
        instantiated_cm = object()
        stream_context_manager_mock.return_value = instantiated_cm
        context_manager = emitter.open_stream("some text")

    assert emitter.printer_calls == []
    assert context_manager is instantiated_cm
    assert stream_context_manager_mock.mock_calls == [
        call(emitter._printer, "some text", stream=None, use_timestamp=False, ephemeral_mode=True),
    ]


def test_openstream_in_brief_mode(get_initiated_emitter):
    """Return a stream context manager with stderr as the output stream and ephemeral mode."""
    emitter = get_initiated_emitter(EmitterMode.BRIEF)

    with patch("craft_cli.messages._StreamContextManager") as stream_context_manager_mock:
        instantiated_cm = object()
        stream_context_manager_mock.return_value = instantiated_cm
        context_manager = emitter.open_stream("some text")

    assert emitter.printer_calls == []
    assert context_manager is instantiated_cm
    assert stream_context_manager_mock.mock_calls == [
        call(
            emitter._printer,
            "some text",
            stream=sys.stderr,
            use_timestamp=False,
            ephemeral_mode=True,
        ),
    ]


def test_openstream_in_verbose_mode(get_initiated_emitter):
    """Return a stream context manager with stderr as the output stream."""
    emitter = get_initiated_emitter(EmitterMode.VERBOSE)

    with patch("craft_cli.messages._StreamContextManager") as stream_context_manager_mock:
        instantiated_cm = object()
        stream_context_manager_mock.return_value = instantiated_cm
        context_manager = emitter.open_stream("some text")

    assert emitter.printer_calls == []
    assert context_manager is instantiated_cm
    assert stream_context_manager_mock.mock_calls == [
        call(
            emitter._printer,
            "some text",
            stream=sys.stderr,
            use_timestamp=False,
            ephemeral_mode=False,
        ),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
def test_openstream_in_developer_modes(get_initiated_emitter, mode):
    """Return a stream context manager with stderr as the output stream."""
    emitter = get_initiated_emitter(mode)

    with patch("craft_cli.messages._StreamContextManager") as stream_context_manager_mock:
        instantiated_cm = object()
        stream_context_manager_mock.return_value = instantiated_cm
        context_manager = emitter.open_stream("some text")

    assert emitter.printer_calls == []
    assert context_manager is instantiated_cm
    assert stream_context_manager_mock.mock_calls == [
        call(
            emitter._printer,
            "some text",
            stream=sys.stderr,
            use_timestamp=True,
            ephemeral_mode=False,
        ),
    ]


def test_openstream_no_text(get_initiated_emitter):
    """Test open_stream() with no text parameter."""
    emitter = get_initiated_emitter(EmitterMode.VERBOSE)

    with patch("craft_cli.messages._StreamContextManager") as stream_context_manager_mock:
        instantiated_cm = object()
        stream_context_manager_mock.return_value = instantiated_cm
        context_manager = emitter.open_stream()

    assert emitter.printer_calls == []
    assert context_manager is instantiated_cm
    assert stream_context_manager_mock.mock_calls == [
        call(
            emitter._printer,
            None,
            stream=sys.stderr,
            use_timestamp=False,
            ephemeral_mode=False,
        ),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.BRIEF,
    ],
)
def test_verbose_in_quietish_modes(get_initiated_emitter, mode):
    """Only log the message."""
    emitter = get_initiated_emitter(mode)
    emitter.verbose("some text")

    assert emitter.printer_calls == [
        call().show(None, "some text", use_timestamp=False),
    ]


def test_verbose_in_verbose_mode(get_initiated_emitter):
    """Log the message and show it in stderr."""
    emitter = get_initiated_emitter(EmitterMode.VERBOSE)
    emitter.verbose("some text")

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=False),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
def test_verbose_in_developer_modes(get_initiated_emitter, mode):
    """Only log the message."""
    emitter = get_initiated_emitter(mode)
    emitter.verbose("some text")

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=True),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.BRIEF,
        EmitterMode.VERBOSE,
    ],
)
def test_debug_in_more_quietish_modes(get_initiated_emitter, mode):
    """Only log the message."""
    emitter = get_initiated_emitter(mode)
    emitter.debug("some text")

    assert emitter.printer_calls == [
        call().show(None, "some text", use_timestamp=True),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.DEBUG,
        EmitterMode.TRACE,
    ],
)
def test_debug_in_developer_modes(get_initiated_emitter, mode):
    """Only log the message."""
    emitter = get_initiated_emitter(mode)
    emitter.debug("some text")

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=True),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.BRIEF,
        EmitterMode.VERBOSE,
        EmitterMode.DEBUG,
    ],
)
def test_trace_in_non_trace_modes(get_initiated_emitter, mode):
    """Only log the message."""
    emitter = get_initiated_emitter(mode)
    emitter.trace("some text")
    assert emitter.printer_calls == []


def test_trace_in_trace_mode(get_initiated_emitter):
    """Log the message and show it in stderr."""
    emitter = get_initiated_emitter(EmitterMode.TRACE)
    emitter.trace("some text")

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=True),
    ]


# -- tests for stopping the machinery ok


def test_ended_ok(get_initiated_emitter):
    """Finish everything ok."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    emitter.ended_ok()

    assert emitter.printer_calls == [call().stop()]


def test_ended_double_after_ok(get_initiated_emitter):
    """Support double ending."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    emitter.ended_ok()
    emitter.printer_calls.clear()

    emitter.ended_ok()
    assert emitter.printer_calls == []


def test_ended_double_after_error(get_initiated_emitter):
    """Support double ending."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    emitter.error(CraftError("test message"))
    emitter.printer_calls.clear()

    emitter.ended_ok()
    assert emitter.printer_calls == []

@pytest.mark.parametrize("method", emitter_methods(init=True, exclude=["init", "ended_ok", "error"]))
def test_needs_being_active(method):
    """Check that calling public methods needs emitter to not be stopped."""
    with pytest.raises(RuntimeError, match="Emitter is stopped already"):
        method()


# -- tests for pausing the machinery


def test_paused_resumed_ok(get_initiated_emitter, tmp_path):
    """The Emitter is paused and resumed fine after a successful body run."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)

    with emitter.pause():
        assert emitter.printer_calls == [
            # the pausing message is shown and emitter is stopped
            call().show(None, "Emitter: Pausing control of the terminal", use_timestamp=True),
            call().stop(),
        ]
        emitter.printer_calls.clear()
        # we end ok here

    # a new Printer is created, with same logpath and the resuming message is shown
    assert emitter.printer_calls == [
        call(str(tmp_path / FAKE_LOG_NAME)),
        call().show(None, "Emitter: Resuming control of the terminal", use_timestamp=True),
    ]


def test_paused_resumed_error(get_initiated_emitter, tmp_path):
    """The Emitter is paused and resumed fine even if an exception is raised."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)

    with pytest.raises(ValueError):
        with emitter.pause():
            assert emitter.printer_calls == [
                # the pausing message is shown and emitter is stopped
                call().show(None, "Emitter: Pausing control of the terminal", use_timestamp=True),
                call().stop(),
            ]
            emitter.printer_calls.clear()

            # something bad goes here; note the exception should not be hidden (that's why
            # all this is inside a `pytest.raises`, but the emitter should resume ok
            raise ValueError()

    # a new Printer is created, with same logpath and the resuming message is shown
    assert emitter.printer_calls == [
        call(str(tmp_path / FAKE_LOG_NAME)),
        call().show(None, "Emitter: Resuming control of the terminal", use_timestamp=True),
    ]


def test_paused_cant_show(get_initiated_emitter, tmp_path):
    """The Emitter cannot show messages when paused."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)

    with emitter.pause():
        with pytest.raises(RuntimeError):
            emitter.trace("fruta")


# -- tests for error reporting


@pytest.mark.parametrize("mode", [EmitterMode.QUIET, EmitterMode.BRIEF, EmitterMode.VERBOSE])
def test_reporterror_simple_message_final_user_modes(mode, get_initiated_emitter):
    """Report just a simple message, in final user modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=False, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.DEBUG, EmitterMode.TRACE])
def test_reporterror_simple_message_developer_modes(mode, get_initiated_emitter):
    """Report just a simple message, in developer intended modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=True, end_line=True),
        call().stop(),
    ]


def test_reporterror_detailed_info_quiet_modes(get_initiated_emitter):
    """Report an error having detailed information, in final user modes.

    Check that "quiet" is indeed quiet.
    """
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    error = CraftError("test message", details="boom")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(None, "Detailed information: boom", use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=False, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.BRIEF, EmitterMode.VERBOSE])
def test_reporterror_detailed_info_final_user_modes(mode, get_initiated_emitter):
    """Report an error having detailed information, in final user modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message", details="boom")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(sys.stderr, "Detailed information: boom", use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=False, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.DEBUG, EmitterMode.TRACE])
def test_reporterror_detailed_info_developer_modes(mode, get_initiated_emitter):
    """Report an error having detailed information, in developer intended modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message", details="boom")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "Detailed information: boom", use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=True, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.QUIET, EmitterMode.BRIEF, EmitterMode.VERBOSE])
def test_reporterror_chained_exception_final_user_modes(mode, get_initiated_emitter):
    """Report an error that was originated after other exception, in final user modes."""
    emitter = get_initiated_emitter(mode)
    orig_exception = None
    try:
        try:
            raise ValueError("original")
        except ValueError as err:
            orig_exception = err
            raise CraftError("test message") from err
    except CraftError as err:
        error = err

    with patch("craft_cli.messages._get_traceback_lines") as tblines_mock:
        tblines_mock.return_value = ["traceback line 1", "traceback line 2"]
        emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(None, "traceback line 1", use_timestamp=False, end_line=True),
        call().show(None, "traceback line 2", use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=False, end_line=True),
        call().stop(),
    ]

    # check the traceback lines are generated using the original exception
    tblines_mock.assert_called_with(orig_exception)


@pytest.mark.parametrize("mode", [EmitterMode.DEBUG, EmitterMode.TRACE])
def test_reporterror_chained_exception_developer_modes(mode, get_initiated_emitter):
    """Report an error that was originated after other exception, in developer intended modes."""
    emitter = get_initiated_emitter(mode)
    orig_exception = None
    try:
        try:
            raise ValueError("original")
        except ValueError as err:
            orig_exception = err
            raise CraftError("test message") from err
    except CraftError as err:
        error = err

    with patch("craft_cli.messages._get_traceback_lines") as tblines_mock:
        tblines_mock.return_value = ["traceback line 1", "traceback line 2"]
        emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "traceback line 1", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "traceback line 2", use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=True, end_line=True),
        call().stop(),
    ]

    # check the traceback lines are generated using the original exception
    tblines_mock.assert_called_with(orig_exception)


@pytest.mark.parametrize("mode", [EmitterMode.QUIET, EmitterMode.BRIEF, EmitterMode.VERBOSE])
def test_reporterror_with_resolution_final_user_modes(mode, get_initiated_emitter):
    """Report an error with a recommended resolution, in final user modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message", resolution="run")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(sys.stderr, "Recommended resolution: run", use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=False, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.DEBUG, EmitterMode.TRACE])
def test_reporterror_with_resolution_developer_modes(mode, get_initiated_emitter):
    """Report an error with a recommended resolution, in developer intended modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message", resolution="run")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "Recommended resolution: run", use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=True, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.QUIET, EmitterMode.BRIEF, EmitterMode.VERBOSE])
def test_reporterror_with_docs_final_user_modes(mode, get_initiated_emitter):
    """Report including a docs url, in final user modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message", docs_url="https://charmhub.io/docs/whatever")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    full_docs_message = "For more information, check out: https://charmhub.io/docs/whatever"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_docs_message, use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=False, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.DEBUG, EmitterMode.TRACE])
def test_reporterror_with_docs_developer_modes(mode, get_initiated_emitter):
    """Report including a docs url, in developer intended modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message", docs_url="https://charmhub.io/docs/whatever")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    full_docs_message = "For more information, check out: https://charmhub.io/docs/whatever"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_docs_message, use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=True, end_line=True),
        call().stop(),
    ]


def test_reporterror_full_complete(get_initiated_emitter):
    """Sanity case to check order between the different parts."""
    emitter = get_initiated_emitter(EmitterMode.TRACE)
    try:
        try:
            raise ValueError("original")
        except ValueError as err:
            raise CraftError(
                "test message",
                details="boom",
                resolution="run",
                docs_url="https://charmhub.io/docs/whatever",
            ) from err
    except CraftError as err:
        error = err

    with patch("craft_cli.messages._get_traceback_lines") as tblines_mock:
        tblines_mock.return_value = ["traceback line 1", "traceback line 2"]
        emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    full_docs_message = "For more information, check out: https://charmhub.io/docs/whatever"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "Detailed information: boom", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "traceback line 1", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "traceback line 2", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "Recommended resolution: run", use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_docs_message, use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=True, end_line=True),
        call().stop(),
    ]


def test_reporterror_double_after_ok(get_initiated_emitter):
    """Support error reporting after ending."""
    emitter = get_initiated_emitter(EmitterMode.TRACE)
    emitter.ended_ok()
    emitter.printer_calls.clear()

    emitter.error(CraftError("test message"))
    assert emitter.printer_calls == []


def test_reporterror_double_after_error(get_initiated_emitter):
    """Support error reporting after ending."""
    emitter = get_initiated_emitter(EmitterMode.TRACE)
    emitter.error(CraftError("test message"))
    emitter.printer_calls.clear()

    emitter.error(CraftError("test message"))
    assert emitter.printer_calls == []


def test_reporterror_no_logpath(get_initiated_emitter):
    """The log path is not reported if indicated."""
    emitter = get_initiated_emitter(EmitterMode.TRACE)
    error = CraftError("test message", logpath_report=False)
    emitter.error(error)

    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=True, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize(
    ("docs_base_url", "doc_slug"),
    [
        ("https://documentation.ubuntu.com/testcraft", "reference/error.html"),
        ("https://documentation.ubuntu.com/testcraft/", "reference/error.html"),
        ("https://documentation.ubuntu.com/testcraft", "/reference/error.html"),
        ("https://documentation.ubuntu.com/testcraft/", "/reference/error.html"),
    ],
)
def test_reporterror_doc_slug(get_initiated_emitter, docs_base_url, doc_slug):
    emitter = get_initiated_emitter(EmitterMode.BRIEF, docs_base_url=docs_base_url)
    error = CraftError("test message", logpath_report=False, doc_slug=doc_slug)
    emitter.error(error)

    full_docs_message = (
        "For more information, check out: "
        "https://documentation.ubuntu.com/testcraft/reference/error.html"
    )
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_docs_message, use_timestamp=False, end_line=True),
        call().stop(),
    ]


def test_reporterror_both_url_and_slug(get_initiated_emitter):
    docs_base_url = "https://base-url.ubuntu.com/testcraft"
    doc_slug = "/slug"
    full_url = "https://full-url.ubuntu.com/testcraft/full"
    emitter = get_initiated_emitter(EmitterMode.BRIEF, docs_base_url=docs_base_url)

    # An error with both docs_url and doc_slug
    error = CraftError("test message", logpath_report=False, docs_url=full_url, doc_slug=doc_slug)
    emitter.error(error)

    full_docs_message = f"For more information, check out: {full_url}"

    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_docs_message, use_timestamp=False, end_line=True),
        call().stop(),
    ]


def test_reporterror_command_error(get_initiated_emitter):
    stderr = b":: an error occurred\n:: on this line ^^\n"
    error = CraftCommandError("test message", stderr=stderr, logpath_report=False)

    emitter = get_initiated_emitter(EmitterMode.BRIEF)
    emitter.error(error)

    expected = "Captured error:\n:: an error occurred\n:: on this line ^^\n"

    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(sys.stderr, expected, use_timestamp=False, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("stderr", [None, "", b""])
def test_reporterror_command_error_no_stderr(get_initiated_emitter, stderr):
    error = CraftCommandError("test message", stderr=stderr, logpath_report=False)

    emitter = get_initiated_emitter(EmitterMode.BRIEF)
    emitter.error(error)

    expected = "Captured error:\n:: an error occurred\n:: on this line ^^\n"

    # No "Captured error (...)" output
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().stop(),
    ]


# -- Tests for confirming a yes/no question with the user.

def test_confirm_with_user_defaults_with_tty(
    get_initiated_emitter,
    emitter_mode: EmitterMode,
    mock_input,
    mock_isatty
):
    mock_input.return_value = ""
    mock_isatty.return_value = True
    emit = get_initiated_emitter(emitter_mode)

    assert emit.confirm("prompt", default=True) is True
    assert mock_input.mock_calls == [call("prompt [Y/n]: ")]
    mock_input.reset_mock()

    assert emit.confirm("prompt", default=False) is False
    assert mock_input.mock_calls == [call("prompt [y/N]: ")]


def test_confirm_with_user_defaults_without_tty(get_initiated_emitter, emitter_mode, mock_input, mock_isatty):
    mock_isatty.return_value = False
    emit = get_initiated_emitter(emitter_mode)

    assert emit.confirm("prompt", default=True) is True
    assert emit.confirm("prompt", default=False) is False

    assert mock_input.mock_calls == []


@pytest.mark.parametrize(
    ("user_input", "expected"),
    [
        ("y", True),
        ("Y", True),
        ("yes", True),
        ("YES", True),
        ("n", False),
        ("N", False),
        ("no", False),
        ("NO", False),
        (" Yes sir Mr. Callahan Sir!", True),
        (" nah yeah? Yeah nah!    ", False)
    ],
)
@pytest.mark.usefixtures("mock_isatty")
def test_confirm_with_user(get_initiated_emitter, user_input, expected, mock_input, emitter_mode):
    mock_input.return_value = user_input
    emit = get_initiated_emitter(emitter_mode)

    assert emit.confirm("prompt") == expected
    assert mock_input.mock_calls == [call("prompt [y/N]: ")]


@pytest.fixture
def initiated_emitter(get_initiated_emitter, mock_isatty, emitter_mode) -> Emitter:
    return cast(Emitter, get_initiated_emitter(emitter_mode))


@pytest.fixture
def fake_input(initiated_emitter: Emitter) -> Callable[[str], Callable[[str], str]]:
    def get_fake_input_wrapper(input_val: str) -> Callable[[str], str]:
        def _inner(prompt: str) -> str:
            assert initiated_emitter._stopped
            return input_val

        return _inner

    return get_fake_input_wrapper


def test_confirm_with_user_pause_emitter(
    initiated_emitter: Emitter,
    fake_input: Callable[[str], Callable[[str], str]],
    mocker,
):
    """The emitter should be paused when using the terminal."""
    mocker.patch("builtins.input", fake_input(""))

    initiated_emitter.confirm("prompt")


def test_prompt_returns_user_input(
    initiated_emitter: Emitter,
    fake_input: Callable[[str], Callable[[str], str]],
    mocker: pytest_mock.MockerFixture,
):
    """The emitter should return user input."""
    mocker.patch("builtins.input", fake_input("some-input"))

    assert initiated_emitter.prompt("prompt") == "some-input"


def test_prompt_returns_secret_input(
    initiated_emitter: Emitter,
    fake_input: Callable[[str], Callable[[str], str]],
    mocker: pytest_mock.MockerFixture,
):
    """The emitter should return user secret input."""
    mocker.patch("getpass.getpass", fake_input("some-secret-input"))

    assert initiated_emitter.prompt("prompt", hide=True) == "some-secret-input"

def test_prompt_errors_out_without_tty(
    get_initiated_emitter, mock_isatty: mock.MagicMock, emitter_mode,
):
    """The emitter should error out if no tty available."""
    mock_isatty.return_value = False
    emit = get_initiated_emitter(emitter_mode)

    with pytest.raises(CraftError, match="prompting not possible without tty"):
        emit.prompt("no prompting without tty!")

def test_prompt_does_not_allow_empty_input(
    initiated_emitter: Emitter,
    fake_input: Callable[[str], Callable[[str], str]],
    mocker: pytest_mock.MockerFixture,
):
    """The emitter should not allow empty input."""
    mocker.patch("builtins.input", fake_input(""))

    with pytest.raises(CraftError, match="input cannot be empty") as error:
        initiated_emitter.prompt("prompt")
