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

"""Generic fixtures for the whole test suite."""

import pytest

from craft_cli.printer import Printer, _Spinner


class RecordingSpinner(_Spinner):
    """A Spinner that records what is sent to supervision."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.supervised = []

    def supervise(self, message):
        self.supervised.append(message)


class RecordingPrinter(Printer):
    """A Printer isolated from outputs.

    Instead, it records all messages to print.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.written_terminal_lines = []
        self.written_terminal_bars = []
        self.written_captured_lines = []
        self.written_captured_bars = []
        self.logged = []
        self.spinner = RecordingSpinner(self)
        self.spinner.start()

    def _write_line_terminal(self, message, *, spintext=None):
        """Overwrite the real one to avoid it and record the message and maybe the spintext."""
        if spintext is not None:
            self.written_terminal_lines.append((message, spintext))
        else:
            self.written_terminal_lines.append(message)

    def _write_bar_terminal(self, message):
        """Overwrite the real one to avoid it and record the message."""
        self.written_terminal_bars.append(message)

    def _write_line_captured(self, message):
        """Overwrite the real one to avoid it and record the message."""
        self.written_captured_lines.append(message)

    def _write_bar_captured(self, message):
        """Overwrite the real one to avoid it and record the message."""
        self.written_captured_bars.append(message)

    def _log(self, message):
        """Overwrite the real one to avoid it and record the message."""
        self.logged.append(message)


@pytest.fixture
def recording_printer(tmp_path):
    """Provide a recording printer."""
    recording_printer = RecordingPrinter(tmp_path / "test.log")
    yield recording_printer
    if not recording_printer.stopped:
        recording_printer.stop()
