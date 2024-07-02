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

"""Support for all messages, ok or after errors, to screen and log file."""

from __future__ import annotations

__all__ = [
    "EmitterMode",
    "TESTMODE",
    "emit",
]

import enum
import functools
import logging
import os
import pathlib
import select
import sys
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Generator, Literal, TextIO, TypeVar, cast

import platformdirs

try:
    import win32pipe  # type: ignore[import]

    _WINDOWS_MODE = True
except ImportError:
    _WINDOWS_MODE = False

from craft_cli.printer import Printer

if TYPE_CHECKING:
    from types import TracebackType

    from typing_extensions import Self

    from craft_cli import errors


EmitterMode = enum.Enum("EmitterMode", "QUIET BRIEF VERBOSE DEBUG TRACE")
"""The different modes the Emitter can be set."""

# the limit to how many log files to have
_MAX_LOG_FILES = 5

# the size of bytes chunk that the pipe reader will read at once
_PIPE_READER_CHUNK_SIZE = 4096

# set to true when running *application* tests so some behaviours change (see
# craft_cli/pytest_plugin.py )
TESTMODE = False


def _get_log_filepath(appname: str) -> pathlib.Path:
    """Provide a unique filepath for logging.

    The app name is used for both the directory where the logs are located and each log name.

    Rules:
    - use an platformdirs provided directory
    - base filename is <appname>.<timestamp with microseconds>.log
    - it rotates until it gets to reaches :data:`._MAX_LOG_FILES`
    - after limit is achieved, remove the exceeding files
    - ignore other non-log files in the directory

    Existing files are not renamed (no need, as each name is unique) nor gzipped (they may
    be currently in use by another process).
    """
    basedir = pathlib.Path(platformdirs.user_log_dir(appname))
    filename = f"{appname}-{datetime.now():%Y%m%d-%H%M%S.%f}.log"

    # ensure the basedir is there
    basedir.mkdir(exist_ok=True, parents=True)

    # check if we have too many logs in the dir, and remove the exceeding ones (note
    # that the defined limit includes the about-to-be-created file, that's why the "-1")
    present_files = list(basedir.glob(f"{appname}-*.log"))
    limit = _MAX_LOG_FILES - 1
    if len(present_files) > limit:
        for fpath in sorted(present_files)[:-limit]:
            # ignore if it's not there anymore, which can happen if this code is exercised in
            # parallel or when tearing down instances
            fpath.unlink(missing_ok=True)

    return basedir / filename


def _get_traceback_lines(exc: BaseException) -> Generator[str, None, None]:
    """Get the traceback lines (if any) from an exception."""
    tback_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    for tback_line in tback_lines:
        yield from tback_line.rstrip().split("\n")


class _Progresser:
    """A context manager to follow progress on any specific action."""

    def __init__(  # noqa: PLR0913 (too many arguments)
        self,
        printer: Printer,
        total: float,
        text: str,
        stream: TextIO | None,
        delta: bool,  # noqa: FBT001 (boolean positional arg)
        use_timestamp: bool,  # noqa: FBT001 (boolean positional arg)
        ephemeral_context: bool,  # noqa: FBT001 (boolean positional arg)
    ) -> None:
        self.printer = printer
        self.total = total
        self.text = text
        self.accumulated: int | float = 0
        self.stream = stream
        self.delta = delta
        self.use_timestamp = use_timestamp

        # this is only for the "before" and "after" messages; the progress itself
        # is always ephemeral
        self.ephemeral_context = ephemeral_context

    def __enter__(self) -> Self:
        text = f"{self.text} (--->)"
        self.printer.show(
            self.stream, text, ephemeral=self.ephemeral_context, use_timestamp=self.use_timestamp
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        text = f"{self.text} (<---)"
        self.printer.show(
            self.stream, text, ephemeral=self.ephemeral_context, use_timestamp=self.use_timestamp
        )
        return False  # do not consume any exception

    def advance(self, amount: float) -> None:
        """Show a progress bar according to the informed advance."""
        if amount < 0:
            raise ValueError("The advance amount cannot be negative")
        if self.delta:
            self.accumulated += amount
        else:
            self.accumulated = amount
        self.printer.progress_bar(
            self.stream,
            self.text,
            progress=self.accumulated,
            total=self.total,
            use_timestamp=self.use_timestamp,
        )


class _PipeReaderThread(threading.Thread):
    """A thread that reads bytes from a pipe and write lines to the Printer.

    The core part of reading the pipe and stopping work differently according to the platform:

    - posix: use `select` with a timeout: if has data write it to Printer, if the stop flag
        is set just quit

    - windows: read in a blocking way, so the `stop` method will write a byte to unblock it
        after setting the stop flag (this extra byte is handled by the reading code)
    """

    # byte used to unblock the reading (under Windows)
    UNBLOCK_BYTE = b"\x00"

    def __init__(
        self, printer: Printer, stream: TextIO | None, printer_flags: dict[str, bool]
    ) -> None:
        super().__init__()
        self.printer_flags = printer_flags

        # declare the types to satisfy mypy
        self.read_pipe: int
        self.write_pipe: int

        # prepare the pipe pair: the one to read (used in the thread core loop) and the
        # one which is to be written externally (and also used internally under windows
        # to unblock the reading); also note that the pipe pair themselves depend
        # on the platform
        if _WINDOWS_MODE:
            # parameters: default security, default buffer size, binary mode
            binary_mode = os.O_BINARY
            # ignoring the type of the first parameter below, as documentation allows to use None
            # to make it use a NULL security descriptor:
            #     https://www.markjour.com/docs/pywin32-docs/PySECURITY_ATTRIBUTES.html
            self.read_pipe, self.write_pipe = win32pipe.FdCreatePipe(None, 0, binary_mode)  # type: ignore[reportGeneralTypeIssues]
        else:
            self.read_pipe, self.write_pipe = os.pipe()

        # special flag used to stop the pipe reader thread
        self.stop_flag = False

        # where to collect the content that is being read but yet not written (waiting for
        # a newline)
        self.remaining_content = b""

        # printer and stream to write the assembled lines
        self.printer = printer
        self.stream = stream

    def _write(self, data: bytes) -> None:
        """Convert the byte stream into unicode lines and send it to the printer."""
        pointer = 0
        data = self.remaining_content + data
        while True:
            # get the position of next newline (find starts in pointer position)
            newline_position = data.find(b"\n", pointer)

            # no more newlines, store the rest of data for the next time and break
            if newline_position == -1:
                self.remaining_content = data[pointer:]
                break

            # get the useful line and update pointer for next cycle (plus one, to
            # skip the new line itself)
            useful_line = data[pointer:newline_position]
            pointer = newline_position + 1

            # write the useful line to intended outputs. Decode with errors="replace"
            # here because we don't know where this line is coming from.
            unicode_line = useful_line.decode("utf8", errors="replace")
            # replace tabs with a set number of spaces so that the printer
            # can correctly count the characters.
            unicode_line = unicode_line.replace("\t", "  ")
            text = f":: {unicode_line}"
            self.printer.show(self.stream, text, **self.printer_flags)

    def _run_posix(self) -> None:
        """Run the thread, handling pipes in the POSIX way."""
        poller = select.poll()
        poller.register(self.read_pipe, select.POLLIN)
        while True:
            rlist = poller.poll(0.1)
            if len(rlist) != 0:
                data = os.read(self.read_pipe, _PIPE_READER_CHUNK_SIZE)
                self._write(data)
            elif self.stop_flag:
                # only quit when nothing left to read
                break
        poller.unregister(self.read_pipe)

    def _run_windows(self) -> None:
        """Run the thread, handling pipes in the Windows way."""
        while True:
            data = os.read(self.read_pipe, _PIPE_READER_CHUNK_SIZE)  # blocking!

            # data is sliced to get bytes (if checked the last position we get a number)
            if self.stop_flag and data[-1:] == self.UNBLOCK_BYTE:
                # we are flagged to stop and did read until the unblock byte: write any
                # remaining data and quit
                data = data[:-1]
                if data:
                    self._write(data)
                break

            if data:
                self._write(data)

    def run(self) -> None:
        """Run the thread."""
        if _WINDOWS_MODE:
            self._run_windows()
        else:
            self._run_posix()

    def stop(self) -> None:
        """Stop the thread.

        This flag ourselves to quit, but then makes the main thread (which is the one calling
        this method) to wait ourselves to finish.

        Under Windows it inserts an extra byte in the pipe to unblock the reading.
        """
        self.stop_flag = True
        if _WINDOWS_MODE:
            os.write(self.write_pipe, self.UNBLOCK_BYTE)
        self.join()
        os.close(self.read_pipe)
        os.close(self.write_pipe)


class _StreamContextManager:
    """A context manager that provides a pipe for subprocess to write its output."""

    def __init__(  # noqa: PLR0913 (too many arguments)
        self,
        printer: Printer,
        text: str | None,
        stream: TextIO | None,
        use_timestamp: bool,  # noqa: FBT001 (boolean positional arg)
        ephemeral_mode: bool,  # noqa: FBT001 (boolean positional arg)
    ) -> None:
        # prepare the printer flags for the initial message and everything produced
        # by the pipe reader
        printer_flags = {
            "use_timestamp": use_timestamp,
            "ephemeral": ephemeral_mode,
            "end_line": not ephemeral_mode,
        }

        if text is not None:
            # show the intended text (explicitly asking for a complete line) before
            # passing the output command to the pipe-reading thread
            printer.show(stream, text, **printer_flags)

        # enable the thread to read and show what comes through the provided pipe
        self.pipe_reader = _PipeReaderThread(printer, stream, printer_flags)

    def __enter__(self) -> int:
        self.pipe_reader.start()
        return self.pipe_reader.write_pipe

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        self.pipe_reader.stop()
        return False  # do not consume any exception


class _Handler(logging.Handler):
    """A logging handler that emits messages through the core Printer."""

    def __init__(
        self, printer: Printer, streaming_brief: bool = False  # noqa: FBT001, FBT002
    ) -> None:
        """Init the handler.

        :param printer:
            The Printer to emit captured log messages.
        :param bool streaming_brief:
            Whether log records of levels higher than DEBUG should be print (ephemerally)
            when in BRIEF mode.
        """
        super().__init__()
        self.printer = printer
        self.streaming_brief = streaming_brief

        # level is 0 so we get EVERYTHING (as we need to send it all to the log file), and
        # will decide on "emit" if also goes to screen using the custom mode
        self.level = 0
        self.mode = EmitterMode.QUIET

    def emit(self, record: logging.LogRecord) -> None:
        """Send the message in the LogRecord to the printer."""
        # under DEBUG level only in trace mode, the rest is not even logged
        if record.levelno < logging.DEBUG and self.mode != EmitterMode.TRACE:
            return

        if self.mode in (EmitterMode.QUIET, EmitterMode.BRIEF):
            # no stream in more quietish modes
            stream = None
        elif self.mode == EmitterMode.VERBOSE:
            # in verbose, only info, warning, error, etc
            stream = sys.stderr if record.levelno > logging.DEBUG else None
        elif self.mode == EmitterMode.DEBUG:
            # in debug mode, also include debug log level
            stream = sys.stderr if record.levelno >= logging.DEBUG else None
        else:
            # in trace, everything
            stream = sys.stderr

        text = record.getMessage()

        ephemeral = False
        if self.mode == EmitterMode.BRIEF and self.streaming_brief:
            stream = sys.stderr if record.levelno > logging.DEBUG else None
            ephemeral = True

        use_timestamp = self.mode in (EmitterMode.DEBUG, EmitterMode.TRACE)
        self.printer.show(stream, text, use_timestamp=use_timestamp, ephemeral=ephemeral)


FuncT = TypeVar("FuncT", bound=Callable[..., Any])


def _active_guard(ignore_when_stopped: bool = False) -> Callable[..., Any]:  # noqa: FBT001, FBT002
    """Decorate Emitter methods to be called when active.

    It will check that the emitter is initiated and that is not stopped (except when
    ignore_when_stopped=True, in that case the call will be ignored, to support
    double-ending).
    """

    def decorator(wrapped_func: FuncT) -> FuncT:
        @functools.wraps(wrapped_func)
        def func(self: Emitter, *args: Any, **kwargs: Any) -> Any:
            if not self._initiated:
                raise RuntimeError("Emitter needs to be initiated first")
            if self._stopped:
                if ignore_when_stopped:
                    return None
                raise RuntimeError("Emitter is stopped already")
            return wrapped_func(self, *args, **kwargs)

        return cast(FuncT, func)

    return decorator


class Emitter:
    """Main interface to all the messages emitting functionality.

    This handles everything that goes to screen and to the log file, even interfacing
    with the formal logging infrastructure to get messages from it.

    This class is not meant to be instantiated by the application, just use `emit` from
    this module.

    The user of this object will select any of the following methods according to what
    to show:

    - `message`: for the final output of the running command; if there is important information
      that needs to be shown to the user in the middle of the execution (and not overwritten
      by other messages) this method can be also used but passing intermediate=True.

    - `progress`: for all the progress messages intended to provide information that the
      machinery is running and doing what.

    - `trace`: for all the messages that may used by the *developers* to do any debugging on
      the application behaviour and/or logs forensics.
    """

    def __init__(self) -> None:
        # these attributes will be set at "real init time", with the `init` method below
        self._greeting: str = None  # type: ignore[assignment]
        self._printer: Printer = None  # type: ignore[assignment]
        self._mode: EmitterMode = None  # type: ignore[assignment]
        self._initiated = False
        self._stopped = False
        self._log_filepath: pathlib.Path = None  # type: ignore[assignment]
        self._log_handler: _Handler = None  # type: ignore[assignment]
        self._streaming_brief = False
        self._docs_base_url: str | None = None

    def init(  # noqa: PLR0913 (too many arguments)
        self,
        mode: EmitterMode,
        appname: str,
        greeting: str,
        log_filepath: pathlib.Path | None = None,
        *,
        streaming_brief: bool = False,
        docs_base_url: str | None = None,
    ) -> None:
        """Initialize the emitter; this must be called once and before emitting any messages.

        :param streaming_brief: Whether informational messages should be streamed with
            progress messages when using BRIEF mode (see example 29).
        :param docs_base_url: The base address of the documentation, for error reporting
            purposes.
        """
        if self._initiated:
            if TESTMODE:
                self._stop()
            else:
                raise RuntimeError("Double Emitter init detected!")

        self._greeting = greeting
        self._streaming_brief = streaming_brief

        self._docs_base_url = docs_base_url
        if docs_base_url and docs_base_url.endswith("/"):
            self._docs_base_url = docs_base_url[:-1]

        # create a log file, bootstrap the printer, and before anything else send the greeting
        # to the file
        self._log_filepath = _get_log_filepath(appname) if log_filepath is None else log_filepath
        self._printer = Printer(self._log_filepath)
        self._printer.show(None, greeting)

        # hook into the logging system
        logger = logging.getLogger()
        self._log_handler = _Handler(self._printer, streaming_brief=streaming_brief)
        logger.addHandler(self._log_handler)

        self._initiated = True
        self._stopped = False
        self.set_mode(mode)

    @_active_guard()
    def get_mode(self) -> EmitterMode:
        """Return the mode of the emitter."""
        return self._mode

    @_active_guard()
    def set_mode(self, mode: EmitterMode) -> None:
        """Set the mode of the emitter."""
        self._mode = mode
        self._log_handler.mode = mode

        if mode in (EmitterMode.VERBOSE, EmitterMode.DEBUG, EmitterMode.TRACE):
            use_timestamp = mode in (EmitterMode.DEBUG, EmitterMode.TRACE)

            # send the greeting to the screen before any further messages
            msgs = [
                self._greeting,
                f"Logging execution to {str(self._log_filepath)!r}",
            ]
            for msg in msgs:
                self._printer.show(
                    sys.stderr, msg, use_timestamp=use_timestamp, avoid_logging=True, end_line=True
                )

    @_active_guard()
    def message(self, text: str) -> None:
        """Show an important message to the user.

        Normally used as the final message, to show the result of a command.
        """
        stream = None if self._mode == EmitterMode.QUIET else sys.stdout
        if self._streaming_brief:
            # Clear the message prefix, as this message stands alone
            self._printer.set_terminal_prefix("")
        self._printer.show(stream, text)

    @_active_guard()
    def verbose(self, text: str) -> None:
        """Verbose information.

        Useful to provide more information to the user that shouldn't be exposed
        when in brief mode for clarity and simplicity.
        """
        if self._mode in (EmitterMode.QUIET, EmitterMode.BRIEF):
            stream = None
            use_timestamp = False
        elif self._mode == EmitterMode.VERBOSE:
            stream = sys.stderr
            use_timestamp = False
        else:
            stream = sys.stderr
            use_timestamp = True
        self._printer.show(stream, text, use_timestamp=use_timestamp)

    @_active_guard()
    def debug(self, text: str) -> None:
        """Debug information.

        To record everything that the user may not want to normally see but useful
        for the app developers to understand why things are failing or performing
        forensics on the produced logs.
        """
        if self._mode in (EmitterMode.QUIET, EmitterMode.BRIEF, EmitterMode.VERBOSE):
            stream = None
        else:
            stream = sys.stderr
        self._printer.show(stream, text, use_timestamp=True)

    @_active_guard()
    def trace(self, text: str) -> None:
        """Trace information.

        A way to expose system-generated information, about the general process or
        particular information, which in general would be too overwhelming for
        debugging purposes but sometimes needed for particular analysis.

        It only produces information to the screen and into the logs if in TRACE mode.
        """
        # as we're not even logging anything if not in TRACE mode, instead of calling the
        # Printer with no stream and the 'avoid_logging' flag (which would be more consistent
        # with the rest of the Emitter methods, in this case we just avoid moving any
        # machinery as much as possible, because potentially there will be huge number
        # of trace calls.
        if self._mode == EmitterMode.TRACE:
            self._printer.show(sys.stderr, text, use_timestamp=True)

    def _get_progress_params(
        self, permanent: bool  # noqa: FBT001 (boolean positional arg)
    ) -> tuple[TextIO | None, bool, bool]:
        """Calculate the different parameters for progress information."""
        if self._mode == EmitterMode.QUIET:
            # will not be shown in the screen (always logged to the file)
            stream = None
            use_timestamp = False
            ephemeral = True
        elif self._mode == EmitterMode.BRIEF:
            # show the indicated message to stderr (ephemeral, unless flag is used) and log it
            stream = sys.stderr
            use_timestamp = False
            ephemeral = not permanent
        elif self._mode == EmitterMode.VERBOSE:
            # show the indicated message to stderr (permanent) and log it
            stream = sys.stderr
            use_timestamp = False
            ephemeral = False
        else:
            # show to stderr with timestamp (permanent), and log it
            stream = sys.stderr
            use_timestamp = True
            ephemeral = False
        return stream, use_timestamp, ephemeral

    @_active_guard()
    def progress(self, text: str, permanent: bool = False) -> None:  # noqa: FBT001, FBT002
        """Progress information for a multi-step command.

        This is normally used to present several separated text messages.

        If a progress message is important enough that it should not be overwritten by the
        next ones, use 'permanent=True'.

        These messages will be truncated to the terminal's width, and overwritten by the next
        line (unless verbose/trace mode).
        """
        stream, use_timestamp, ephemeral = self._get_progress_params(permanent)

        if self._streaming_brief:
            # Clear the "new thing" prefix, as this is a new progress message.
            self._printer.set_terminal_prefix("")

        self._printer.show(stream, text, ephemeral=ephemeral, use_timestamp=use_timestamp)

        if self._mode == EmitterMode.BRIEF and ephemeral and self._streaming_brief:
            # Set the "progress prefix" for upcoming non-permanent messages.
            self._printer.set_terminal_prefix(text)

    @_active_guard()
    def progress_bar(
        self, text: str, total: float, delta: bool = True  # noqa: FBT001, FBT002
    ) -> _Progresser:
        """Progress information for a potentially long-running single step of a command.

        E.g. a download or provisioning step.

        Returns a context manager with a `.advance` method to call on each progress (passing the
        delta progress, unless delta=False here, which implies that the calls to `.advance` should
        pass the total so far).
        """
        stream, use_timestamp, ephemeral = self._get_progress_params(permanent=False)
        return _Progresser(self._printer, total, text, stream, delta, use_timestamp, ephemeral)

    @_active_guard()
    def open_stream(self, text: str | None = None) -> _StreamContextManager:
        """Open a stream context manager to get messages from subprocesses."""
        if self._mode == EmitterMode.QUIET:
            # no third party stream
            stream = None
            ephemeral = True
            use_timestamp = False
        elif self._mode == EmitterMode.BRIEF:
            stream = sys.stderr
            ephemeral = True
            use_timestamp = False
        elif self._mode == EmitterMode.VERBOSE:
            # third party stream to stderr
            stream = sys.stderr
            ephemeral = False
            use_timestamp = False
        else:
            # third party stream to stderr with timestamp
            stream = sys.stderr
            ephemeral = False
            use_timestamp = True
        return _StreamContextManager(
            self._printer,
            text,
            stream=stream,
            use_timestamp=use_timestamp,
            ephemeral_mode=ephemeral,
        )

    @_active_guard()
    @contextmanager
    def pause(self) -> Generator[None, None, None]:
        """Context manager that pauses and resumes the control of the terminal.

        Note that no messages will be collected while paused, not even for logging.
        """
        self.debug("Emitter: Pausing control of the terminal")
        self._printer.stop()
        self._stopped = True
        try:
            yield
        finally:
            self._stopped = False
            self._printer = self._log_handler.printer = Printer(self._log_filepath)
            self.debug("Emitter: Resuming control of the terminal")

    def _stop(self) -> None:
        """Do all the stopping."""
        self._printer.stop()
        self._stopped = True

    @_active_guard(ignore_when_stopped=True)
    def ended_ok(self) -> None:
        """Finish the messaging system gracefully."""
        self._stop()

    def _report_error(self, error: errors.CraftError) -> None:
        """Report the different message lines from a CraftError."""
        if self._mode in (EmitterMode.QUIET, EmitterMode.BRIEF, EmitterMode.VERBOSE):
            use_timestamp = False
            full_stream = None
        else:
            use_timestamp = True
            full_stream = sys.stderr

        # the initial message
        self._printer.show(sys.stderr, str(error), use_timestamp=use_timestamp, end_line=True)

        # detailed information and/or original exception
        if error.details:
            text = f"Detailed information: {error.details}"
            self._printer.show(full_stream, text, use_timestamp=use_timestamp, end_line=True)
        if error.__cause__:
            for line in _get_traceback_lines(error.__cause__):
                self._printer.show(full_stream, line, use_timestamp=use_timestamp, end_line=True)

        # hints for the user to know more
        if error.resolution:
            text = f"Recommended resolution: {error.resolution}"
            self._printer.show(sys.stderr, text, use_timestamp=use_timestamp, end_line=True)

        doc_url = None
        if self._docs_base_url and error.doc_slug:
            doc_url = self._docs_base_url + error.doc_slug
        if error.docs_url:
            doc_url = error.docs_url

        if doc_url:
            text = f"For more information, check out: {doc_url}"
            self._printer.show(sys.stderr, text, use_timestamp=use_timestamp, end_line=True)

        # expose the logfile path only if indicated
        if error.logpath_report:
            text = f"Full execution log: {str(self._log_filepath)!r}"
            self._printer.show(sys.stderr, text, use_timestamp=use_timestamp, end_line=True)

    @_active_guard(ignore_when_stopped=True)
    def error(self, error: errors.CraftError) -> None:
        """Handle the system's indicated error and stop machinery."""
        if self._streaming_brief:
            # Clear the message prefix, as this error stands alone
            self._printer.set_terminal_prefix("")
        self._report_error(error)
        self._stop()

    @_active_guard()
    def set_secrets(self, secrets: list[str]) -> None:
        """Set the list of strings that should be masked out in all output."""
        self._printer.set_secrets(secrets)


# module-level instantiated Emitter; this is the instance all code shall use and Emitter
# shall not be instantiated again for the process' run
emit = Emitter()
