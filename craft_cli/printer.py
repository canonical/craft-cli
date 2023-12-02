# Copyright 2023 Canonical Ltd.
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

"""The output (for different destinations) handler and helper functions."""

from __future__ import annotations

import itertools
import math
import queue
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Callable, TextIO

if TYPE_CHECKING:
    import pathlib

# the char used to draw the progress bar ('FULL BLOCK')
_PROGRESS_BAR_SYMBOL = "█"

# seconds before putting the spinner to work
_SPINNER_THRESHOLD = 2

# seconds between each spinner char
_SPINNER_DELAY = 0.1

# set to true when running *application* tests so some behaviours change (see
# craft_cli/pytest_plugin.py )
TESTMODE = False


@dataclass
class _MessageInfo:
    """Comprehensive information for a message that may go to screen and log."""

    stream: TextIO | None
    text: str
    ephemeral: bool = False
    bar_progress: int | float | None = None
    bar_total: int | float | None = None
    use_timestamp: bool = False
    end_line: bool = False
    created_at: datetime = field(default_factory=datetime.now, compare=False)
    terminal_prefix: str = ""


@lru_cache
def _stream_is_terminal(stream: TextIO | None) -> bool:
    is_a_terminal = getattr(stream, "isatty", lambda: False)()
    return is_a_terminal and _get_terminal_width() > 0


def _get_terminal_width() -> int:
    """Return the number of columns of the terminal."""
    return shutil.get_terminal_size().columns


def _format_term_line(prefix: str, text: str, spintext: str, *, ephemeral: bool) -> str:
    """Format a line to print to the terminal."""
    # fill with spaces until the very end, on one hand to clear a possible previous message,
    # but also to always have the cursor at the very end
    width = _get_terminal_width()
    usable = width - len(spintext) - 1  # the 1 is the cursor itself
    if len(text) > usable:
        if ephemeral:
            text = text[: usable - 1] + "…"
        elif spintext:
            # we need to rewrite the message with the spintext, use only the last line for
            # multiline messages, and ensure (again) that the last real line fits
            remaining_for_last_line = len(text) % width
            text = text[-remaining_for_last_line:]
            if len(text) > usable:
                text = text[: usable - 1] + "…"
    cleaner = " " * (usable - len(text) % width)

    return prefix + text + spintext + cleaner


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

    def __init__(self, printer: Printer) -> None:
        super().__init__()
        # special flag used to stop the spinner thread
        self.stop_flag = object()

        # daemon mode, so if the app crashes this thread does not holds everything
        self.daemon = True

        # communication from the printer
        self.queue: queue.Queue[Any] = queue.Queue()

        # hold the printer, to make it spin
        self.printer = printer

        # a lock to wait the spinner to stop spinning
        self.lock = threading.Lock()

        # Keep the message under supervision available for examination.
        self._under_supervision: _MessageInfo | None = None

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

    def supervise(self, message: _MessageInfo | None) -> None:
        """Supervise a message to spin it if it remains too long."""
        # Don't bother the spinner if we're repeating the same message
        if message == self._under_supervision:
            return

        self._under_supervision = message
        self.queue.put(message)
        # (maybe) wait for the spinner to exit spinning state (which does some cleaning)
        self.lock.acquire()
        self.lock.release()

    def stop(self) -> None:
        """Stop self."""
        self.queue.put(self.stop_flag)
        self.join()


class Printer:
    """Handle writing the different messages to the different outputs (out, err and log).

    If TESTMODE is True, this class changes its behaviour: the spinner is never started,
    so there is no thread polluting messages when running tests if they take too long to run.
    """

    def __init__(self, log_filepath: pathlib.Path) -> None:
        self.stopped = False

        # holder of the previous message
        self.prv_msg: _MessageInfo | None = None

        # open the log file (will be closed explicitly later)
        self.log = log_filepath.open("at", encoding="utf8")

        # keep account of output terminal streams with unfinished lines
        self.unfinished_stream: TextIO | None = None

        self.terminal_prefix = ""

        self.secrets: list[str] = []

        # run the spinner supervisor
        self.spinner = _Spinner(self)
        if not TESTMODE:
            self.spinner.start()

    def set_terminal_prefix(self, prefix: str) -> None:
        """Set the string to be prepended to every message shown to the terminal."""
        self.terminal_prefix = prefix

    def _get_prefixed_message_text(self, message: _MessageInfo) -> str:
        """Get the message's text with the proper terminal prefix, if any."""
        text = message.text
        prefix = message.terminal_prefix

        # Don't repeat text: can happen due to the spinner.
        if prefix and text != prefix:
            separator = ":: "

            # Don't duplicate the separator, which can come from multiple different
            # sources.
            if text.startswith(separator):
                separator = ""

            text = f"{prefix} {separator}{text}"

        return text

    def _write_line_terminal(self, message: _MessageInfo, *, spintext: str = "") -> None:
        """Write a simple line message to the screen."""
        # prepare the text with (maybe) the timestamp
        text = self._get_prefixed_message_text(message)

        if message.use_timestamp:
            timestamp_str = message.created_at.isoformat(sep=" ", timespec="milliseconds")
            text = f"{timestamp_str} {text}"

        if spintext:
            # forced to overwrite the previous message to present the spinner
            maybe_cr = "\r"
        elif self.prv_msg is None or self.prv_msg.end_line:
            # first message, or previous message completed the line: start clean
            maybe_cr = ""
        elif self.prv_msg.ephemeral:
            # the last one was ephemeral, overwrite it
            maybe_cr = "\r"
            if self.prv_msg.stream != message.stream:
                # If the last message's stream is different from this new one,
                # send the carriage return to the original stream only.
                print(maybe_cr, flush=True, file=self.prv_msg.stream, end="")
                maybe_cr = ""
        else:
            # complete the previous line, leaving that message ok
            maybe_cr = ""
            print(flush=True, file=self.prv_msg.stream)

        # We don't need to rewrite the same ephemeral message repeatedly.
        should_overwrite = spintext or message.end_line or not message.ephemeral
        if should_overwrite or message != self.prv_msg:
            line = _format_term_line(maybe_cr, text, spintext, ephemeral=message.ephemeral)
            print(line, end="", flush=True, file=message.stream)

        if message.end_line:
            # finish the just shown line, as we need a clean terminal for some external thing
            print(flush=True, file=message.stream)
            self.unfinished_stream = None
        else:
            self.unfinished_stream = message.stream

    def _write_line_captured(self, message: _MessageInfo) -> None:
        """Write a simple line message to a captured output."""
        # prepare the text with (maybe) the timestamp
        if message.use_timestamp:
            timestamp_str = message.created_at.isoformat(sep=" ", timespec="milliseconds")
            text = timestamp_str + " " + message.text
        else:
            text = message.text

        print(text, file=message.stream)

    def _write_bar_terminal(self, message: _MessageInfo) -> None:
        """Write a progress bar to the screen."""
        # prepare the text with (maybe) the timestamp
        if message.use_timestamp:
            timestamp_str = message.created_at.isoformat(sep=" ", timespec="milliseconds")
            text = timestamp_str + " " + message.text
        else:
            text = message.text

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

        if message.bar_progress is None or message.bar_total is None:  # pragma: no cover
            # Should not happen as the caller checks the message
            raise ValueError("Tried to write a bar message with invalid attributes")

        numerical_progress = f"{message.bar_progress}/{message.bar_total}"
        bar_percentage = min(message.bar_progress / message.bar_total, 1)

        # terminal size minus the text and numerical progress, and 5 (the cursor at the end,
        # two spaces before and after the bar, and two surrounding brackets)
        terminal_width = _get_terminal_width()
        bar_width = terminal_width - len(text) - len(numerical_progress) - 5

        # only show the bar with progress if there is enough space, otherwise just the
        # message (truncated, if needed)
        if bar_width > 0:
            completed_width = math.floor(bar_width * min(bar_percentage, 100))
            completed_bar = _PROGRESS_BAR_SYMBOL * completed_width
            empty_bar = " " * (bar_width - completed_width)
            line = f"{maybe_cr}{text} [{completed_bar}{empty_bar}] {numerical_progress}"
        else:
            text = text[: terminal_width - 1]  # space for cursor
            line = f"{maybe_cr}{text}"

        print(line, end="", flush=True, file=message.stream)
        self.unfinished_stream = message.stream

    def _write_bar_captured(self, message: _MessageInfo) -> None:
        """Do not write any progress bar to the captured output."""

    def _show(self, msg: _MessageInfo) -> None:
        """Show the composed message."""
        # show the message in one way or the other only if there is a stream
        if msg.stream is None:
            return

        # the writing functions depend on the final output: if the stream is captured or it's
        # a real terminal
        write_line: Callable[[_MessageInfo], None]
        if _stream_is_terminal(msg.stream):
            write_line = self._write_line_terminal
            write_bar = self._write_bar_terminal
        else:
            write_line = self._write_line_captured
            write_bar = self._write_bar_captured

        if msg.bar_progress is None:
            # regular message, send it to the spinner and write it
            self.spinner.supervise(msg)
            write_line(msg)
        else:
            # progress bar, send None to the spinner (as it's not a "spinnable" message)
            # and write it
            self.spinner.supervise(None)
            write_bar(msg)
        self.prv_msg = msg

    def _log(self, message: _MessageInfo) -> None:
        """Write the line message to the log file."""
        # prepare the text with (maybe) the timestamp
        timestamp_str = message.created_at.isoformat(sep=" ", timespec="milliseconds")
        self.log.write(f"{timestamp_str} {message.text}\n")
        # Flush the file: protect a bit in case of crashes, and multiprocess-based
        # parallelism.
        self.log.flush()

    def spin(self, message: _MessageInfo, spintext: str) -> None:
        """Write a line message including a spin text, only to a terminal."""
        if _stream_is_terminal(message.stream):
            self._write_line_terminal(message, spintext=spintext)

    def show(  # noqa: PLR0913 (too many parameters)
        self,
        stream: TextIO | None,
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

        text = self._apply_secrets(text)

        msg = _MessageInfo(
            stream=stream,
            text=text.rstrip(),
            ephemeral=ephemeral,
            use_timestamp=use_timestamp,
            end_line=end_line,
            terminal_prefix=self._apply_secrets(self.terminal_prefix),
        )
        self._show(msg)
        if not avoid_logging:
            self._log(msg)

    def progress_bar(  # noqa: PLR0913
        self,
        stream: TextIO | None,
        text: str,
        *,
        progress: float,
        total: float,
        use_timestamp: bool,
    ) -> None:
        """Show a progress bar to the given stream."""
        text = self._apply_secrets(text)

        msg = _MessageInfo(
            stream=stream,
            text=text.rstrip(),
            bar_progress=progress,
            bar_total=total,
            ephemeral=True,  # so it gets eventually overwritten by other message
            use_timestamp=use_timestamp,
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
            # With unfinished_stream set, the prv_msg object is valid.
            if self.prv_msg is not None and self.prv_msg.ephemeral:
                # If the last printed message is of 'ephemeral' type, the stop
                # request must clean and reset the line.
                cleaner = " " * (_get_terminal_width() - 1)
                line = "\r" + cleaner + "\r"
                print(line, end="", flush=True, file=self.prv_msg.stream)
            else:
                # The last printed message is permanent. Leave the cursor on
                # the next clean line.
                print(flush=True, file=self.unfinished_stream)

        self.log.close()
        self.stopped = True

    def set_secrets(self, secrets: list[str]) -> None:
        """Set the list of strings that should be masked out in all outputs."""
        # Keep a copy, to protect against clients modifying the list on accident.
        self.secrets = secrets.copy()

    def _apply_secrets(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, "*****")
        return text
