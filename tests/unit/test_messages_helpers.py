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

"""Tests that check the different helpers in the messages module."""

import datetime
import logging
import re
import sys
import time
from unittest.mock import MagicMock, call

import platformdirs
import pytest

from craft_cli import messages
from craft_cli.messages import (
    EmitterMode,
    _get_log_filepath,
    _get_traceback_lines,
    _Handler,
    _MessageInfo,
    _Printer,
    _Progresser,
    _Spinner,
)

# -- tests for the log filepath provider


@pytest.fixture
def test_log_dir(tmp_path, monkeypatch):
    """Provide a test log filepath, also fixing platformdirs to use a temp dir."""
    dirpath = tmp_path / "testlogdir"
    dirpath.mkdir()
    monkeypatch.setattr(platformdirs, "user_log_dir", lambda appname: dirpath / appname)
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

    # compare using less or equal because in Windows time passes differently
    assert before <= timestamp <= after


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
    time.sleep(0.01)  # sleep a little so new log file has a different timestamp
    new_fpath = _get_log_filepath("testapp")
    new_fpath.touch()
    present_logs = sorted((test_log_dir / "testapp").iterdir())
    assert present_logs == [previous_fpath, new_fpath]


def test_getlogpath_several_files_already_present(test_log_dir, monkeypatch):
    """There are several files in the destination dir."""
    monkeypatch.setattr(messages, "_MAX_LOG_FILES", 100)
    previous_fpath = _get_log_filepath("testapp")
    previous_fpath.touch()
    time.sleep(0.01)  # sleep a little so new log file has a different timestamp
    new_fpath = _get_log_filepath("testapp")
    new_fpath.touch()
    present_logs = sorted((test_log_dir / "testapp").iterdir())
    assert present_logs == [previous_fpath, new_fpath]


def test_getlogpath_hit_rotation_limit(test_log_dir, monkeypatch):
    """The rotation limit is hit."""
    monkeypatch.setattr(messages, "_MAX_LOG_FILES", 3)
    previous_fpaths = []
    for _ in range(2):
        fpath = _get_log_filepath("testapp")
        fpath.touch()
        previous_fpaths.append(fpath)
        time.sleep(0.01)  # sleep a little so different log files have different timestamps
    new_fpath = _get_log_filepath("testapp")
    new_fpath.touch()
    present_logs = sorted((test_log_dir / "testapp").iterdir())
    assert present_logs == previous_fpaths + [new_fpath]


def test_getlogpath_exceeds_rotation_limit(test_log_dir, monkeypatch):
    """The rotation limit is exceeded."""
    monkeypatch.setattr(messages, "_MAX_LOG_FILES", 3)
    previous_fpaths = []
    for _ in range(3):
        fpath = _get_log_filepath("testapp")
        fpath.touch()
        previous_fpaths.append(fpath)
        time.sleep(0.01)  # sleep a little so different log files have different timestamps
    new_fpath = _get_log_filepath("testapp")
    new_fpath.touch()
    present_logs = sorted((test_log_dir / "testapp").iterdir())
    assert present_logs == previous_fpaths[1:] + [new_fpath]


def test_getlogpath_ignore_other_files(test_log_dir, monkeypatch):
    """Only affect logs of the given app."""
    monkeypatch.setattr(messages, "_MAX_LOG_FILES", 3)

    # old files to trigger some removal
    previous_fpaths = []
    for _ in range(3):
        fpath = _get_log_filepath("testapp")
        fpath.touch()
        previous_fpaths.append(fpath)
        time.sleep(0.01)  # sleep a little so different log files have different timestamps

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


def test_getlogpath_deep_dirs(tmp_path, monkeypatch):
    """The log directory is inside a path that does not exist yet."""
    dirpath = tmp_path / "foo" / "bar" / "testlogdir"
    monkeypatch.setattr(platformdirs, "user_log_dir", lambda appname: dirpath / appname)
    fpath = _get_log_filepath("testapp")

    # check the file is inside the proper dir and that it exists
    assert fpath.parent == dirpath / "testapp"
    assert fpath.parent.exists


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
    expected_texts = (
        r" - \(\d\.\ds\)",
        r" \\ \(\d\.\ds\)",
        r" | \(\d\.\ds\)",
        r" / \(\d\.\ds\)",
        r" - \(\d\.\ds\)",
    )
    for expected, real in zip(expected_texts, spinned_texts):
        assert re.match(expected, real)

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


def test_spinner_silent_on_complete_messages(spinner, monkeypatch):
    """Nothing happens before the threshold time."""
    monkeypatch.setattr(messages, "_SPINNER_THRESHOLD", 0.001)
    spinner.supervise(_MessageInfo(sys.stdout, "test msg 1", end_line=True))

    # enough time for activation
    time.sleep(0.05)

    assert spinner.printer.spinned == []


# -- tests for the _Handler class


@pytest.fixture
def handler(monkeypatch):
    """Provide a handler hooked to the logging system and with a patched printer."""
    handler = _Handler(MagicMock())
    logger = logging.getLogger()
    logger.setLevel(0)
    logger.addHandler(handler)
    return handler


def test_handler_init(handler):
    """Default _Handler values."""
    assert isinstance(handler, logging.Handler)
    assert handler.level == 0
    assert handler.mode == EmitterMode.QUIET  # type: ignore


def test_handler_emit_full_message(handler):
    """Check how the text is retrieved from the logging system."""
    handler.mode = EmitterMode.QUIET
    logging.getLogger().error("test message %s", 23)

    assert handler.printer.mock_calls == [
        call.show(sys.stderr, "test message 23", use_timestamp=False),
    ]


def test_handler_emit_quiet(handler):
    """Check emit behaviour in QUIET mode."""
    handler.mode = EmitterMode.QUIET

    logger = logging.getLogger()
    logger.error("test error")
    logger.warning("test warning")
    logger.info("test info")
    logger.debug("test debug")

    assert handler.printer.mock_calls == [
        call.show(sys.stderr, "test error", use_timestamp=False),
        call.show(sys.stderr, "test warning", use_timestamp=False),
        call.show(None, "test info", use_timestamp=False),
        call.show(None, "test debug", use_timestamp=False),
    ]


def test_handler_emit_normal(handler):
    """Check emit behaviour in NORMAL mode."""
    handler.mode = EmitterMode.NORMAL

    logger = logging.getLogger()
    logger.error("test error")
    logger.warning("test warning")
    logger.info("test info")
    logger.debug("test debug")

    assert handler.printer.mock_calls == [
        call.show(sys.stderr, "test error", use_timestamp=False),
        call.show(sys.stderr, "test warning", use_timestamp=False),
        call.show(sys.stderr, "test info", use_timestamp=False),
        call.show(None, "test debug", use_timestamp=False),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.VERBOSE, EmitterMode.TRACE])
def test_handler_emit_verboseish(handler, mode):
    """Check emit behaviour in more verbose modes."""
    handler.mode = mode

    logger = logging.getLogger()
    logger.error("test error")
    logger.warning("test warning")
    logger.info("test info")
    logger.debug("test debug")

    assert handler.printer.mock_calls == [
        call.show(sys.stderr, "test error", use_timestamp=True),
        call.show(sys.stderr, "test warning", use_timestamp=True),
        call.show(sys.stderr, "test info", use_timestamp=True),
        call.show(sys.stderr, "test debug", use_timestamp=True),
    ]


# -- tests for the traceback lines extractor


def test_traceback_lines_simple():
    """Extract traceback lines from an exception."""
    try:
        raise ValueError("pumba")
    except ValueError as err:
        tbacklines = list(_get_traceback_lines(err))

    # disable 'black' here otherwise it complains about pylint comment (which we need for
    # pylint to shut up about the false positive)
    # fmt: off
    assert tbacklines[0] == "Traceback (most recent call last):"  # pylint: disable=used-before-assignment
    assert tbacklines[1].startswith("  File ")
    assert tbacklines[1].endswith(", in test_traceback_lines_simple")
    assert tbacklines[2] == '    raise ValueError("pumba")'
    assert tbacklines[3] == "ValueError: pumba"
