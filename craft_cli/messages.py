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
import pathlib
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TextIO, Union

import appdirs


@dataclass
class _MessageInfo:
    """Comprehensive information for a message that may go to screen and log."""

    stream: Union[TextIO, None]
    text: str
    use_timestamp: bool = False
    end_line: bool = False
    created_at: datetime = field(default_factory=datetime.now)


# the different modes the Emitter can be set
EmitterMode = enum.Enum("EmitterMode", "QUIET NORMAL VERBOSE TRACE")

# the limit to how many log files to have
_MAX_LOG_FILES = 5


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


class _Printer:
    """Handle writing the different messages to the different outputs (out, err and log)."""

    def __init__(self, log_filepath: pathlib.Path) -> None:
        # holder of the previous message
        self.prv_msg: Optional[_MessageInfo] = None

        # the open log file (will be closed explicitly when the thread ends)
        self.log = open(log_filepath, "wt", encoding="utf8")  # pylint: disable=consider-using-with

        # keep account of output streams with unfinished lines
        self.unfinished_stream: Optional[TextIO] = None

    def _write_line(self, message: _MessageInfo) -> None:
        """Write a simple line message to the screen."""
        # prepare the text with (maybe) the timestamp
        if message.use_timestamp:
            timestamp_str = message.created_at.isoformat(sep=" ", timespec="milliseconds")
            text = timestamp_str + " " + message.text
        else:
            text = message.text

        if self.prv_msg is not None and not self.prv_msg.end_line:
            # complete the previous line, leaving that message ok
            print(flush=True, file=self.prv_msg.stream)

        # fill with spaces until the very end, on one hand to clear a possible previous message,
        # but also to always have the cursor at the very end
        width = _get_terminal_width()
        usable = width - 1  # the 1 is the cursor itself
        cleaner = " " * (usable - len(text) % width)

        line = text + cleaner
        print(line, end="", flush=True, file=message.stream)
        if message.end_line:
            # finish the just shown line, as we need a clean terminal for some external thing
            print(flush=True, file=message.stream)
            self.unfinished_stream = None
        else:
            self.unfinished_stream = message.stream

    def _show(self, msg: _MessageInfo) -> None:
        """Show the composed message."""
        # show the message in one way or the other only if there is a stream
        if msg.stream is None:
            return

        # regular message, write it
        self._write_line(msg)
        self.prv_msg = msg

    def _log(self, message: _MessageInfo) -> None:
        """Write the line message to the log file."""
        # prepare the text with (maybe) the timestamp
        timestamp_str = message.created_at.isoformat(sep=" ", timespec="milliseconds")
        self.log.write(f"{timestamp_str} {message.text}\n")

    def show(
        self,
        stream: Optional[TextIO],
        text: str,
        *,
        use_timestamp: bool = False,
        end_line: bool = False,
        avoid_logging: bool = False,
    ) -> None:
        """Show a text to the given stream."""
        msg = _MessageInfo(
            stream=stream,
            text=text.rstrip(),
            use_timestamp=use_timestamp,
            end_line=end_line,
        )
        self._show(msg)
        if not avoid_logging:
            self._log(msg)

    def stop(self) -> None:
        """Stop the printing infrastructure.

        In detail:
        - add a new line to the screen (if needed)
        - close the log file
        """
        if self.unfinished_stream is not None:
            print(flush=True, file=self.unfinished_stream)
        self.log.close()


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
    def ended_ok(self) -> None:
        """Finish the messaging system gracefully."""
        self.printer.stop()  # type: ignore
