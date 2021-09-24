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

"""Support for all messages, ok or after errors, to screen and log file."""

import enum
import itertools
import math
import pathlib
import queue
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, TextIO, Union

import appdirs


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


def _get_terminal_width() -> int:
    """Return the number of columns of the terminal."""
    return shutil.get_terminal_size().columns


def _get_log_filepath(appname: str) -> pathlib.Path:
    """Provide a unique filepath for logging.

    The app name is used for both the directory where the logs are located and each log name.

    Rules:
    - use an appdirs provided directory
    - base filename is <appname>.<timestamp with microseconds>.log
    - it rotates until it gets to reaches :data:`._MAX_LOG_FILES`
    - after limit is achieved, remove the exceeding files
    - ignore other non-log files in the directory

    Existing files are not renamed (no need, as each name is unique) nor gzipped (they may
    be currently in use by another process).
    """
    basedir = pathlib.Path(appdirs.user_log_dir()) / appname
    filename = f"{appname}-{datetime.now():%Y%m%d-%H%M%S.%f}.log"

    # ensure the basedir is there
    basedir.mkdir(exist_ok=True)

    # check if we have too many logs in the dir, and remove the exceeding ones (note
    # that the defined limit includes the about-to-be-created file, that's why the "-1")
    present_files = list(basedir.glob(f"{appname}-*.log"))
    limit = _MAX_LOG_FILES - 1
    if len(present_files) > limit:
        for fpath in sorted(present_files)[:-limit]:
            fpath.unlink()

    return basedir / filename


class _Spinner(threading.Thread):
    """A supervisor thread that will repeat long-standing messages with a spinner besides it."""

    def __init__(self, printer: "_Printer"):
        super().__init__()
        # special flag used to stop itself
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
                if prv_msg is None:
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
    """Handle writing the different messages to the different outputs (out, err and log)."""

    def __init__(self, log_filepath: pathlib.Path) -> None:
        # holder of the previous message
        self.prv_msg: Optional[_MessageInfo] = None

        # the open log file (will be closed explicitly when the thread ends)
        self.log = open(log_filepath, "wt", encoding="utf8")  # pylint: disable=consider-using-with

        # keep account of output streams with unfinished lines
        self.unfinished_stream: Optional[TextIO] = None

        # run the spinner supervisor
        self.spinner = _Spinner(self)
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
            # progress bar, send None to the spinner (as it's not a "spinneable" message)
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
        """Show a text to the given stream."""
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
        self.spinner.stop()
        if self.unfinished_stream is not None:
            print(flush=True, file=self.unfinished_stream)
        self.log.close()


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


def _init_guard(wrapped_func):
    """Decorate Emitter methods to be called *after* init."""

    def func(self, *args, **kwargs):
        if not self.initiated:
            raise RuntimeError("Emitter needs to be initiated first")
        return wrapped_func(self, *args, **kwargs)

    return func


class Emitter:
    """Main interface to all the messages emitting functionality.

    This handles everything that goes to screen and to the log file, even interfacing
    with the formal logging infrastructure to get messages from it.

    This class is not meant to be instantiated by the application, just use `emit` from
    this module.
    """

    def __init__(self):
        # these attributes will be set at "real init time", with the `init` method below
        self.greeting = None
        self.printer = None
        self.mode = None
        self.initiated = False
        self.log_filepath = None

    def init(self, mode: EmitterMode, appname: str, greeting: str):
        """Initialize the emitter; this must be called once and before emitting any messages."""
        self.greeting = greeting

        # create a log file, bootstrap the printer, and before anything else send the greeting
        # to the file
        self.log_filepath = _get_log_filepath(appname)
        self.printer = _Printer(self.log_filepath)
        self.printer.show(None, greeting)

        self.initiated = True
        self.set_mode(mode)

    @_init_guard
    def set_mode(self, mode: EmitterMode) -> None:
        """Set the mode of the emitter."""
        self.mode = mode

        if self.mode == EmitterMode.VERBOSE or self.mode == EmitterMode.TRACE:
            # send the greeting to the screen before any further messages
            msgs = [
                self.greeting,
                f"Logging execution to {str(self.log_filepath)!r}",
            ]
            for msg in msgs:
                self.printer.show(  # type: ignore
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
            intermediate and (self.mode == EmitterMode.VERBOSE or self.mode == EmitterMode.TRACE)
        )
        self.printer.show(sys.stdout, text, use_timestamp=use_timestamp)  # type: ignore

    @_init_guard
    def trace(self, text: str) -> None:
        """Trace/debug information.

        This is to record everything that the user may not want to normally see, but it's
        useful for postmortem analysis.
        """
        stream = sys.stderr if self.mode == EmitterMode.TRACE else None
        self.printer.show(stream, text, use_timestamp=True)  # type: ignore

    @_init_guard
    def progress(self, text: str) -> None:
        """Progress information for a multi-step command.

        This is normally used to present several separated text messages.

        These messages will be truncated to the terminal's width, and overwritten by the next
        line (unless verbose/trace mode).
        """
        if self.mode == EmitterMode.QUIET:
            # will not be shown in the screen (always logged to the file)
            stream = None
            use_timestamp = False
            ephemeral = True
        elif self.mode == EmitterMode.NORMAL:
            # show the indicated message to stderr (ephemeral) and log it
            stream = sys.stderr
            use_timestamp = False
            ephemeral = True
        else:
            # show to stderr with timestamp (permanent), and log it
            stream = sys.stderr
            use_timestamp = True
            ephemeral = False

        self.printer.show(stream, text, ephemeral=ephemeral, use_timestamp=use_timestamp)  # type: ignore

    def progress_bar(self, text: str, total: Union[int, float], delta: bool = True) -> _Progresser:
        """Progress information for a potentially long-running single step of a command.

        E.g. a download or provisioning step.

        Returns a context manager with a `.advance` method to call on each progress (passing the
        delta progress, unless delta=False here, which implies that the calls to `.advance` should
        pass the total so far).
        """
        # don't show progress if quiet
        if self.mode == EmitterMode.QUIET:
            stream = None
        else:
            stream = sys.stderr
        self.printer.show(stream, text, ephemeral=True)  # type: ignore
        return _Progresser(self.printer, total, text, stream, delta)  # type: ignore

    @_init_guard
    def ended_ok(self) -> None:
        """Finish the messaging system gracefully."""
        self.printer.stop()  # type: ignore
