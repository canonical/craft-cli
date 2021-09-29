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

"""Tests that check the different helpers in the messages module."""

import datetime
import re
import sys
import time
from unittest.mock import MagicMock, call

import appdirs
import pytest

from craft_cli import messages
from craft_cli.messages import _get_log_filepath, _MessageInfo, _Printer, _Progresser, _Spinner

# -- tests for the log filepath provider


@pytest.fixture
def test_log_dir(tmp_path, monkeypatch):
    """Provide a test log filepath, also fixing appdirs to use a temp dir."""
    dirpath = tmp_path / "testlogdir"
    dirpath.mkdir()
    monkeypatch.setattr(appdirs, "user_log_dir", lambda: dirpath)
    return dirpath


def test_getlogpath_firstcall(test_log_dir):
    """The very first call."""
    before = datetime.datetime.now()
    fpath = _get_log_filepath("testapp")
    after = datetime.datetime.now()

    # check the file is inside the proper dir and that it exists
    assert fpath.parent == test_log_dir / "testapp"
    assert fpath.parent.exists

    # check the file name format
    match = re.match(r"testapp-(\d+-\d+\.\d+).log", fpath.name)
    assert match
    timestamp = datetime.datetime.strptime(match.groups()[0], "%Y%m%d-%H%M%S.%f")
    assert before < timestamp < after


def test_getlogpath_directory_empty(test_log_dir):
    """Works with the directory already created."""
    parent = test_log_dir / "testapp"
    parent.mkdir()
    fpath = _get_log_filepath("testapp")
    assert fpath.parent == parent


def test_getlogpath_one_file_already_present(test_log_dir):
    """There's already one file in the destination dir."""
    previous_fpath = _get_log_filepath("testapp")
    previous_fpath.touch()
    new_fpath = _get_log_filepath("testapp")
    new_fpath.touch()
    present_logs = sorted((test_log_dir / "testapp").iterdir())
    assert present_logs == [previous_fpath, new_fpath]


def test_getlogpath_several_files_already_present(test_log_dir, monkeypatch):
    """There are several files in the destination dir."""
    monkeypatch.setattr(messages, "_MAX_LOG_FILES", 100)
    previous_fpath = _get_log_filepath("testapp")
    previous_fpath.touch()
    new_fpath = _get_log_filepath("testapp")
    new_fpath.touch()
    present_logs = sorted((test_log_dir / "testapp").iterdir())
    assert present_logs == [previous_fpath, new_fpath]


def test_getlogpath_hit_rotation_limit(test_log_dir, monkeypatch):
    """The rotation limit is hit."""
    monkeypatch.setattr(messages, "_MAX_LOG_FILES", 3)
    previous_fpaths = [_get_log_filepath("testapp") for _ in range(2)]
    for fpath in previous_fpaths:
        fpath.touch()
    new_fpath = _get_log_filepath("testapp")
    new_fpath.touch()
    present_logs = sorted((test_log_dir / "testapp").iterdir())
    assert present_logs == previous_fpaths + [new_fpath]


def test_getlogpath_exceeds_rotation_limit(test_log_dir, monkeypatch):
    """The rotation limit is exceeded."""
    monkeypatch.setattr(messages, "_MAX_LOG_FILES", 3)
    previous_fpaths = [_get_log_filepath("testapp") for _ in range(3)]
    for fpath in previous_fpaths:
        fpath.touch()
    new_fpath = _get_log_filepath("testapp")
    new_fpath.touch()
    present_logs = sorted((test_log_dir / "testapp").iterdir())
    assert present_logs == previous_fpaths[1:] + [new_fpath]


def test_getlogpath_ignore_other_files(test_log_dir, monkeypatch):
    """Only affect logs of the given app."""
    monkeypatch.setattr(messages, "_MAX_LOG_FILES", 3)

    # old files to trigger some removal
    previous_fpaths = [_get_log_filepath("testapp") for _ in range(3)]
    for fpath in previous_fpaths:
        fpath.touch()

    # other stuff that should not be removed
    parent = test_log_dir / "testapp"
    f_aaa = parent / "aaa"
    f_aaa.touch()
    f_zzz = parent / "zzz"
    f_zzz.touch()

    new_fpath = _get_log_filepath("testapp")
    new_fpath.touch()
    present_logs = sorted((test_log_dir / "testapp").iterdir())
    assert present_logs == [f_aaa] + previous_fpaths[1:] + [new_fpath, f_zzz]


# -- tests for the _Progresser class


def test_progresser_absolute_mode():
    """Just use _Progresser as a context manager in absolute mode."""
    stream = sys.stdout
    text = "test text"
    total = 123
    fake_printer = MagicMock()
    with _Progresser(fake_printer, total, text, stream, delta=False) as progresser:
        progresser.advance(20)
        progresser.advance(30.0)

    assert fake_printer.mock_calls == [
        call.progress_bar(stream, text, 20, total),
        call.progress_bar(stream, text, 30.0, total),
    ]


def test_progresser_delta_mode():
    """Just use _Progresser as a context manager in delta mode."""
    stream = sys.stdout
    text = "test text"
    total = 123
    fake_printer = MagicMock()
    with _Progresser(fake_printer, total, text, stream, delta=True) as progresser:
        progresser.advance(20.5)
        progresser.advance(30)

    assert fake_printer.mock_calls == [
        call.progress_bar(stream, text, 20.5, total),
        call.progress_bar(stream, text, 50.5, total),
    ]


@pytest.mark.parametrize("delta", [False, True])
def test_progresser_negative_values(delta):
    """The progress cannot be negative."""
    fake_printer = MagicMock()
    with _Progresser(fake_printer, 123, "test text", sys.stdout, delta=delta) as progresser:
        with pytest.raises(ValueError, match="The advance amount cannot be negative"):
            progresser.advance(-1)


def test_progresser_dont_consume_exceptions():
    """It lets the exceptions go through."""
    fake_printer = MagicMock()
    with pytest.raises(ValueError):
        with _Progresser(fake_printer, 123, "test text", sys.stdout, delta=True):
            raise ValueError()


# -- tests for the _Spinner class


class RecordingPrinter(_Printer):
    """A Printer isolated from outputs; just records spin calls."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.spinned = []

    def spin(self, message, spintext):
        """Overwrite the real one to avoid it and record the message."""
        self.spinned.append((message, spintext))


@pytest.fixture
def spinner(tmp_path):
    """Provide a spinner easy to test.

    Two characteristics:
    - we'll ensure it is stopped
    - use a fake Printer so we can assert on "spin" calls
    """
    spinner = _Spinner(RecordingPrinter(tmp_path / "test.log"))
    spinner.start()
    try:
        yield spinner
    finally:
        spinner.stop()


def test_spinner_daemon(spinner):
    """It should be a daemon."""
    assert spinner.daemon


def test_spinner_working_simple(spinner, monkeypatch):
    """The spinner at work."""
    # set absurdly low times so we can have several spin texts in the test
    monkeypatch.setattr(messages, "_SPINNER_THRESHOLD", 0.001)
    monkeypatch.setattr(messages, "_SPINNER_DELAY", 0.001)

    # send a message, wait enough until we have enough spinned to test, and turn it off
    msg = _MessageInfo(sys.stdout, "test msg")
    spinner.supervise(msg)
    for _ in range(100):
        if len(spinner.printer.spinned) >= 6:
            break
        time.sleep(0.01)
    else:
        pytest.fail("Waited too long for the _Spinner to generate messages")
    spinner.supervise(None)
    to_check = spinner.printer.spinned[:5]

    # check the initial messages complete the "spinner drawing" also showing elapsed time
    spinned_messages, spinned_texts = list(zip(*to_check))
    assert all(spinned_msg is msg for spinned_msg in spinned_messages)
    assert spinned_texts == (
        " - (0.0s)",
        " \\ (0.0s)",
        " | (0.0s)",
        " / (0.0s)",
        " - (0.0s)",
    )

    # the last message should clean the spinner
    assert spinner.printer.spinned[-1] == (msg, " ")


def test_spinner_two_messages(spinner, monkeypatch):
    """Two consecutive messages with spinner."""
    # set absurdly low times so we can have several spin texts in the test
    monkeypatch.setattr(messages, "_SPINNER_THRESHOLD", 0.001)
    monkeypatch.setattr(messages, "_SPINNER_DELAY", 0.001)

    # send a first message, wait enough until we have enough spinned to test
    msg1 = _MessageInfo(sys.stdout, "test msg 1")
    spinner.supervise(msg1)
    for _ in range(100):
        if len(spinner.printer.spinned) >= 6:
            break
        time.sleep(0.01)
    else:
        pytest.fail("Waited too long for the _Spinner to generate messages")

    # send a second message, wait again, and turn it off
    msg2 = _MessageInfo(sys.stdout, "test msg 2")
    spinner.supervise(msg2)
    first_pass_spinned_length = len(spinner.printer.spinned)
    for _ in range(100):
        if len(spinner.printer.spinned) >= first_pass_spinned_length + 6:
            break
        time.sleep(0.01)
    else:
        pytest.fail("Waited too long for the _Spinner to generate messages")
    spinner.supervise(None)

    # check we have two set of messages
    spinned_1 = [sp_text for sp_msg, sp_text in spinner.printer.spinned if sp_msg == msg1]
    spinned_2 = [sp_text for sp_msg, sp_text in spinner.printer.spinned if sp_msg == msg2]
    assert spinned_1 and spinned_2

    # in both cases, the final message should be to clean the spinner
    assert spinned_1[-1] == " "
    assert spinned_2[-1] == " "


def test_spinner_silent_before_threshold(spinner, monkeypatch):
    """Nothing happens before the threshold time."""
    monkeypatch.setattr(messages, "_SPINNER_THRESHOLD", 10)
    spinner.supervise(_MessageInfo(sys.stdout, "test msg 1"))
    spinner.supervise(_MessageInfo(sys.stdout, "test msg 2"))
    assert spinner.printer.spinned == []


def test_spinner_in_the_vacuum(spinner, monkeypatch):
    """There is no spinner without a previous message."""
    # set absurdly low times to for the Spinner to start processing
    monkeypatch.setattr(messages, "_SPINNER_THRESHOLD", 0.001)
    monkeypatch.setattr(messages, "_SPINNER_DELAY", 0.001)

    # enough time for activation
    time.sleep(0.05)

    # nothing spinned, as no message to spin
    assert spinner.printer.spinned == []