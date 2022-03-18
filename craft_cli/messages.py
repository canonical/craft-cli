#
# Copyright 2021-2022 Canonical Ltd.
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

__all__ = [
    "EmitterMode",
    "TESTMODE",
    "emit",
]

import enum
import itertools
import logging
import math
import os
import pathlib
import queue
import select
import shutil
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Literal, Optional, TextIO, Union

import platformdirs

try:
    import win32pipe  # type: ignore

    _WINDOWS_MODE = True
except ImportError:
    _WINDOWS_MODE = False

from craft_cli import errors


@lru_cache
def _stream_is_terminal(stream: Union[TextIO, None]) -> bool:
    return getattr(stream, "isatty", lambda: False)()


@dataclass
class _MessageInfo:  # pylint: disable=too-many-instance-attributes
    """Comprehensive information for a message that may go to screen and log."""

    stream: Union[TextIO, None]
    text: str
    ephemeral: bool = False
    bar_progress: Union[int, float, None] = None
    bar_total: Union[int, float, None] = None
    use_timestamp: bool = False
    end_line: bool = False
    created_at: datetime = field(default_factory=datetime.now)


# the different modes the Emitter can be set
EmitterMode = enum.Enum("EmitterMode", "QUIET NORMAL VERBOSE TRACE")

# the limit to how many log files to have
_MAX_LOG_FILES = 5

# the char used to draw the progress bar ('FULL BLOCK')
_PROGRESS_BAR_SYMBOL = "█"

# seconds before putting the spinner to work
_SPINNER_THRESHOLD = 2

# seconds between each spinner char
_SPINNER_DELAY = 0.1

# the size of bytes chunk that the pipe reader will read at once
_PIPE_READER_CHUNK_SIZE = 4096

# set to true when running *application* tests so some behaviours change
TESTMODE = False


def _get_terminal_width() -> int:
    """Return the number of columns of the terminal."""
    return shutil.get_terminal_size().columns


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
            fpath.unlink()

    return basedir / filename


def _get_traceback_lines(exc: BaseException):
    """Get the traceback lines (if any) from an exception."""
    tback_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    for tback_line in tback_lines:
        for real_line in tback_line.rstrip().split("\n"):
            yield real_line


class _Spinner(threading.Thread):
    """A supervisor thread that will repeat long-standing messages with a spinner besides it.

    This will be a long-lived single thread that will supervise each message received
    through the `supervise` method, and when it stays too long, the printer's `spin`
    will be called with that message and a text to "draw" a spinner, including the elapsed
    time.

    The timing related part of the code uses two constants: _SPINNER_THRESHOLD is how
    many seconds before activating the spinner for the message, and _SPINNER_DELAY is
    the time between `spin` calls.

    When a new message arrives (or None, to indicate that there is nothing to supervise) and
    the previous message was "being spinned", a last `spin` call will be done to clean
    the spinner.
    """

    def __init__(self, printer: "_Printer"):
        super().__init__()
        # special flag used to stop the spinner thread
        self.stop_flag = object()

        # daemon mode, so if the app crashes this thread does not holds everything
        self.daemon = True

        # communication from the printer
        self.queue: queue.Queue = queue.Queue()

        # hold the printer, to make it spin
        self.printer = printer

        # a lock to wait the spinner to stop spinning
        self.lock = threading.Lock()

    def run(self) -> None:
        prv_msg = None
        t_init = time.time()
        while prv_msg is not self.stop_flag:
            try:
                new_msg = self.queue.get(timeout=_SPINNER_THRESHOLD)
            except queue.Empty:
                # waited too much, start to show a spinner (if have a previous message) until
                # we have further info
                if prv_msg is None or prv_msg.end_line:
                    continue
                spinchars = itertools.cycle("-\\|/")
                with self.lock:
                    while True:
                        t_delta = time.time() - t_init
                        spintext = f" {next(spinchars)} ({t_delta:.1f}s)"
                        self.printer.spin(prv_msg, spintext)
                        try:
                            new_msg = self.queue.get(timeout=_SPINNER_DELAY)
                        except queue.Empty:
                            # still nothing! keep going
                            continue
                        # got a new message: clean the spinner and exit from the spinning state
                        self.printer.spin(prv_msg, " ")
                        break

            prv_msg = new_msg
            t_init = time.time()

    def supervise(self, message: Optional[_MessageInfo]) -> None:
        """Supervise a message to spin it if it remains too long."""
        self.queue.put(message)
        # (maybe) wait for the spinner to exit spinning state (which does some cleaning)
        self.lock.acquire()  # pylint: disable=consider-using-with
        self.lock.release()

    def stop(self) -> None:
        """Stop self."""
        self.queue.put(self.stop_flag)
        self.join()


class _Printer:
    """Handle writing the different messages to the different outputs (out, err and log).

    If TESTMODE is True, this class changes its behaviour: the spinner is never started,
    so there is no thread polluting messages when running tests if they take too long to run.
    """

    def __init__(self, log_filepath: pathlib.Path) -> None:
        self.stopped = False

        # holder of the previous message
        self.prv_msg: Optional[_MessageInfo] = None

        # open the log file (will be closed explicitly later)
        self.log = open(log_filepath, "wt", encoding="utf8")  # pylint: disable=consider-using-with

        # keep account of output streams with unfinished lines
        self.unfinished_stream: Optional[TextIO] = None

        # run the spinner supervisor
        self.spinner = _Spinner(self)
        if not TESTMODE:
            self.spinner.start()

    def _write_line(self, message: _MessageInfo, *, spintext: str = "") -> None:
        """Write a simple line message to the screen."""
        # prepare the text with (maybe) the timestamp
        if message.use_timestamp:
            timestamp_str = message.created_at.isoformat(sep=" ", timespec="milliseconds")
            text = timestamp_str + " " + message.text
        else:
            text = message.text

        if spintext:
            # forced to overwrite the previous message to present the spinner
            maybe_cr = "\r"
        elif self.prv_msg is None or self.prv_msg.end_line:
            # first message, or previous message completed the line: start clean
            maybe_cr = ""
        elif self.prv_msg.ephemeral:
            # the last one was ephemeral, overwrite it
            maybe_cr = "\r"
        else:
            # complete the previous line, leaving that message ok
            maybe_cr = ""
            print(flush=True, file=self.prv_msg.stream)

        # fill with spaces until the very end, on one hand to clear a possible previous message,
        # but also to always have the cursor at the very end
        width = _get_terminal_width()
        usable = width - len(spintext) - 1  # the 1 is the cursor itself
        if len(text) > usable:
            if message.ephemeral:
                text = text[: usable - 1] + "…"
            elif spintext:
                # we need to rewrite the message with the spintext, use only the last line for
                # multiline messages, and ensure (again) that the last real line fits
                remaining_for_last_line = len(text) % width
                text = text[-remaining_for_last_line:]
                if len(text) > usable:
                    text = text[: usable - 1] + "…"
        cleaner = " " * (usable - len(text) % width)

        line = maybe_cr + text + spintext + cleaner
        print(line, end="", flush=True, file=message.stream)
        if message.end_line:
            # finish the just shown line, as we need a clean terminal for some external thing
            print(flush=True, file=message.stream)
            self.unfinished_stream = None
        else:
            self.unfinished_stream = message.stream

    def _write_bar(self, message: _MessageInfo) -> None:
        """Write a progress bar to the screen."""
        if self.prv_msg is None or self.prv_msg.end_line:
            # first message, or previous message completed the line: start clean
            maybe_cr = ""
        elif self.prv_msg.ephemeral:
            # the last one was ephemeral, overwrite it
            maybe_cr = "\r"
        else:
            # complete the previous line, leaving that message ok
            maybe_cr = ""
            print(flush=True, file=self.prv_msg.stream)

        numerical_progress = f"{message.bar_progress}/{message.bar_total}"
        bar_percentage = min(message.bar_progress / message.bar_total, 1)  # type: ignore

        # terminal size minus the text and numerical progress, and 5 (the cursor at the end,
        # two spaces before and after the bar, and two surrounding brackets)
        terminal_width = _get_terminal_width()
        bar_width = terminal_width - len(message.text) - len(numerical_progress) - 5

        # only show the bar with progress if there is enough space, otherwise just the
        # message (truncated, if needed)
        if bar_width > 0:
            completed_width = math.floor(bar_width * min(bar_percentage, 100))
            completed_bar = _PROGRESS_BAR_SYMBOL * completed_width
            empty_bar = " " * (bar_width - completed_width)
            line = f"{maybe_cr}{message.text} [{completed_bar}{empty_bar}] {numerical_progress}"
        else:
            text = message.text[: terminal_width - 1]  # space for cursor
            line = f"{maybe_cr}{text}"

        print(line, end="", flush=True, file=message.stream)
        self.unfinished_stream = message.stream

    def _show(self, msg: _MessageInfo) -> None:
        """Show the composed message."""
        # show the message in one way or the other only if there is a stream
        if msg.stream is None:
            return

        if msg.bar_progress is None:
            # regular message, send it to the spinner and write it
            self.spinner.supervise(msg)
            self._write_line(msg)
        else:
            # progress bar, send None to the spinner (as it's not a "spinnable" message)
            # and write it
            self.spinner.supervise(None)
            self._write_bar(msg)
        self.prv_msg = msg

    def _log(self, message: _MessageInfo) -> None:
        """Write the line message to the log file."""
        # prepare the text with (maybe) the timestamp
        timestamp_str = message.created_at.isoformat(sep=" ", timespec="milliseconds")
        self.log.write(f"{timestamp_str} {message.text}\n")

    def spin(self, message: _MessageInfo, spintext: str) -> None:
        """Write a line message including a spin text."""
        if _stream_is_terminal(message.stream):
            self._write_line(message, spintext=spintext)

    def show(
        self,
        stream: Optional[TextIO],
        text: str,
        *,
        ephemeral: bool = False,
        use_timestamp: bool = False,
        end_line: bool = False,
        avoid_logging: bool = False,
    ) -> None:
        """Show a text to the given stream if not stopped."""
        if self.stopped:
            return

        msg = _MessageInfo(
            stream=stream,
            text=text.rstrip(),
            ephemeral=ephemeral,
            use_timestamp=use_timestamp,
            end_line=end_line,
        )
        self._show(msg)
        if not avoid_logging:
            self._log(msg)

    def progress_bar(
        self,
        stream: Optional[TextIO],
        text: str,
        progress: Union[int, float],
        total: Union[int, float],
    ) -> None:
        """Show a progress bar to the given stream."""
        msg = _MessageInfo(
            stream=stream,
            text=text.rstrip(),
            bar_progress=progress,
            bar_total=total,
            ephemeral=True,  # so it gets eventually overwritten by other message
        )
        self._show(msg)

    def stop(self) -> None:
        """Stop the printing infrastructure.

        In detail:
        - stop the spinner
        - add a new line to the screen (if needed)
        - close the log file
        """
        if not TESTMODE:
            self.spinner.stop()
        if self.unfinished_stream is not None:
            print(flush=True, file=self.unfinished_stream)
        self.log.close()
        self.stopped = True


class _Progresser:
    def __init__(  # pylint: disable=too-many-arguments
        self,
        printer: _Printer,
        total: Union[int, float],
        text: str,
        stream: Optional[TextIO],
        delta: bool,
    ):
        self.printer = printer
        self.total = total
        self.text = text
        self.accumulated: Union[int, float] = 0
        self.stream = stream
        self.delta = delta

    def __enter__(self) -> "_Progresser":
        return self

    def __exit__(self, *exc_info) -> Literal[False]:
        return False  # do not consume any exception

    def advance(self, amount: Union[int, float]) -> None:
        """Show a progress bar according to the informed advance."""
        if amount < 0:
            raise ValueError("The advance amount cannot be negative")
        if self.delta:
            self.accumulated += amount
        else:
            self.accumulated = amount
        self.printer.progress_bar(self.stream, self.text, self.accumulated, self.total)


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

    def __init__(self, printer: _Printer, stream: Optional[TextIO]):
        super().__init__()

        # prepare the pipe pair: the one to read (used in the thread core loop) and the
        # one which is to be written externally (and also used internally under windows
        # to unblock the reading); also note that the pipe pair themselves depend
        # on the platform
        if _WINDOWS_MODE:
            # parameters: default security, default buffer size, binary mode
            binary_mode = os.O_BINARY  # pylint: disable=no-member  # (it does exist in Windows!)
            self.read_pipe, self.write_pipe = win32pipe.FdCreatePipe(None, 0, binary_mode)
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

            # write the useful line to intended outputs
            unicode_line = useful_line.decode("utf8")
            text = f":: {unicode_line}"
            self.printer.show(self.stream, text, end_line=True, use_timestamp=True)

    def _run_posix(self) -> None:
        """Run the thread, handling pipes in the POSIX way."""
        while True:
            rlist, _, _ = select.select([self.read_pipe], [], [], 0.1)
            if rlist:
                data = os.read(self.read_pipe, _PIPE_READER_CHUNK_SIZE)
                self._write(data)
            elif self.stop_flag:
                # only quit when nothing left to read
                break

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
            time.sleep(0.1)

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


class _StreamContextManager:
    """A context manager that provides a pipe for subprocess to write its output."""

    def __init__(self, printer: _Printer, text: str, stream: Optional[TextIO]):
        # show the intended text (explicitly asking for a complete line) before passing the
        # output command to the pip-reading thread
        printer.show(stream, text, end_line=True, use_timestamp=True)

        # enable the thread to read and show what comes through the provided pipe
        self.pipe_reader = _PipeReaderThread(printer, stream)

    def __enter__(self):
        self.pipe_reader.start()
        return self.pipe_reader.write_pipe

    def __exit__(self, *exc_info):
        self.pipe_reader.stop()
        return False  # do not consume any exception


class _Handler(logging.Handler):
    """A logging handler that emits messages through the core Printer."""

    # a table to map which logging messages show to the screen according to the selected mode
    mode_to_log_map = {
        EmitterMode.QUIET: logging.WARNING,
        EmitterMode.NORMAL: logging.INFO,
        EmitterMode.VERBOSE: logging.DEBUG,
        EmitterMode.TRACE: logging.DEBUG,
    }

    def __init__(self, printer: _Printer):
        super().__init__()
        self.printer = printer

        # level is 0 so we get EVERYTHING (as we need to send it all to the log file), and
        # will decide on "emit" if also goes to screen using the custom mode
        self.level = 0
        self.mode = EmitterMode.QUIET

    def emit(self, record: logging.LogRecord) -> None:
        """Send the message in the LogRecord to the printer."""
        use_timestamp = self.mode in (EmitterMode.VERBOSE, EmitterMode.TRACE)
        threshold = self.mode_to_log_map[self.mode]
        stream = sys.stderr if record.levelno >= threshold else None
        self.printer.show(stream, record.getMessage(), use_timestamp=use_timestamp)


def _init_guard(wrapped_func):
    """Decorate Emitter methods to be called *after* init."""

    def func(self, *args, **kwargs):
        if not self._initiated:  # pylint: disable=protected-access
            raise RuntimeError("Emitter needs to be initiated first")
        return wrapped_func(self, *args, **kwargs)

    return func


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

    def __init__(self):
        # these attributes will be set at "real init time", with the `init` method below
        self._greeting = None
        self._printer = None
        self._mode = None
        self._initiated = False
        self._stopped = False
        self._log_filepath = None
        self._log_handler = None

    def init(
        self,
        mode: EmitterMode,
        appname: str,
        greeting: str,
        log_filepath: Optional[pathlib.Path] = None,
    ):
        """Initialize the emitter; this must be called once and before emitting any messages."""
        if self._initiated:
            if TESTMODE:
                self._stop()
            else:
                raise RuntimeError("Double Emitter init detected!")

        self._greeting = greeting

        # create a log file, bootstrap the printer, and before anything else send the greeting
        # to the file
        self._log_filepath = _get_log_filepath(appname) if log_filepath is None else log_filepath
        self._printer = _Printer(self._log_filepath)
        self._printer.show(None, greeting)

        # hook into the logging system
        logger = logging.getLogger()
        self._log_handler = _Handler(self._printer)
        logger.addHandler(self._log_handler)

        self._initiated = True
        self._stopped = False
        self.set_mode(mode)

    @_init_guard
    def get_mode(self) -> EmitterMode:
        """Return the mode of the emitter."""
        return self._mode  # type: ignore

    @_init_guard
    def set_mode(self, mode: EmitterMode) -> None:
        """Set the mode of the emitter."""
        self._mode = mode
        self._log_handler.mode = mode  # type: ignore

        if mode in (EmitterMode.VERBOSE, EmitterMode.TRACE):
            # send the greeting to the screen before any further messages
            msgs = [
                self._greeting,
                f"Logging execution to {str(self._log_filepath)!r}",
            ]
            for msg in msgs:
                self._printer.show(  # type: ignore
                    sys.stderr, msg, use_timestamp=True, avoid_logging=True, end_line=True
                )

    @_init_guard
    def message(self, text: str, intermediate: bool = False) -> None:
        """Show an important message to the user.

        Normally used as the final message, to show the result of a command, but it can
        also be used for important messages during the command's execution,
        with intermediate=True (which will include timestamp in verbose/trace mode).
        """
        use_timestamp = bool(
            intermediate and self._mode in (EmitterMode.VERBOSE, EmitterMode.TRACE)
        )
        self._printer.show(sys.stdout, text, use_timestamp=use_timestamp)  # type: ignore

    @_init_guard
    def trace(self, text: str) -> None:
        """Trace/debug information.

        This is to record everything that the user may not want to normally see, but it's
        useful for postmortem analysis.
        """
        stream = sys.stderr if self._mode == EmitterMode.TRACE else None
        self._printer.show(stream, text, use_timestamp=True)  # type: ignore

    @_init_guard
    def progress(self, text: str) -> None:
        """Progress information for a multi-step command.

        This is normally used to present several separated text messages.

        These messages will be truncated to the terminal's width, and overwritten by the next
        line (unless verbose/trace mode).
        """
        if self._mode == EmitterMode.QUIET:
            # will not be shown in the screen (always logged to the file)
            stream = None
            use_timestamp = False
            ephemeral = True
        elif self._mode == EmitterMode.NORMAL:
            # show the indicated message to stderr (ephemeral) and log it
            stream = sys.stderr
            use_timestamp = False
            ephemeral = True
        else:
            # show to stderr with timestamp (permanent), and log it
            stream = sys.stderr
            use_timestamp = True
            ephemeral = False

        self._printer.show(stream, text, ephemeral=ephemeral, use_timestamp=use_timestamp)  # type: ignore

    @_init_guard
    def progress_bar(self, text: str, total: Union[int, float], delta: bool = True) -> _Progresser:
        """Progress information for a potentially long-running single step of a command.

        E.g. a download or provisioning step.

        Returns a context manager with a `.advance` method to call on each progress (passing the
        delta progress, unless delta=False here, which implies that the calls to `.advance` should
        pass the total so far).
        """
        # don't show progress if quiet
        if self._mode == EmitterMode.QUIET:
            stream = None
        else:
            stream = sys.stderr
        self._printer.show(stream, text, ephemeral=True)  # type: ignore
        return _Progresser(self._printer, total, text, stream, delta)  # type: ignore

    @_init_guard
    def open_stream(self, text: str):
        """Open a stream context manager to get messages from subprocesses."""
        # don't show third party streams if quiet or normal
        if self._mode in (EmitterMode.QUIET, EmitterMode.NORMAL):
            stream = None
        else:
            stream = sys.stderr
        return _StreamContextManager(self._printer, text, stream)  # type: ignore

    @_init_guard
    @contextmanager
    def pause(self):
        """Context manager that pauses and resumes the control of the terminal.

        Note that no messages will be collected while paused, not even for logging.
        """
        self.trace("Emitter: Pausing control of the terminal")
        self._printer.stop()  # type: ignore
        try:
            yield
        finally:
            self._printer = _Printer(self._log_filepath)  # type: ignore
            self.trace("Emitter: Resuming control of the terminal")

    def _stop(self) -> None:
        """Do all the stopping."""
        self._printer.stop()  # type: ignore
        self._stopped = True

    @_init_guard
    def ended_ok(self) -> None:
        """Finish the messaging system gracefully."""
        if self._stopped:
            return
        self._stop()

    def _report_error(self, error: errors.CraftError) -> None:
        """Report the different message lines from a CraftError."""
        if self._mode in (EmitterMode.QUIET, EmitterMode.NORMAL):
            use_timestamp = False
            full_stream = None
        else:
            use_timestamp = True
            full_stream = sys.stderr

        # the initial message
        self._printer.show(sys.stderr, str(error), use_timestamp=use_timestamp, end_line=True)  # type: ignore

        # detailed information and/or original exception
        if error.details:
            text = f"Detailed information: {error.details}"
            self._printer.show(full_stream, text, use_timestamp=use_timestamp, end_line=True)  # type: ignore
        if error.__cause__:
            for line in _get_traceback_lines(error.__cause__):
                self._printer.show(full_stream, line, use_timestamp=use_timestamp, end_line=True)  # type: ignore

        # hints for the user to know more
        if error.resolution:
            text = f"Recommended resolution: {error.resolution}"
            self._printer.show(sys.stderr, text, use_timestamp=use_timestamp, end_line=True)  # type: ignore
        if error.docs_url:
            text = f"For more information, check out: {error.docs_url}"
            self._printer.show(sys.stderr, text, use_timestamp=use_timestamp, end_line=True)  # type: ignore

        text = f"Full execution log: {str(self._log_filepath)!r}"
        self._printer.show(sys.stderr, text, use_timestamp=use_timestamp, end_line=True)  # type: ignore

    @_init_guard
    def error(self, error: errors.CraftError) -> None:
        """Handle the system's indicated error and stop machinery."""
        if self._stopped:
            return
        self._report_error(error)
        self._stop()


# module-level instantiated Emitter; this is the instance all code shall use and Emitter
# shall not be instantiated again for the process' run
emit = Emitter()
