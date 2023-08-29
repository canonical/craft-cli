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

"""Tests that check the different helpers in the messages module."""

import datetime
import logging
import pathlib
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
    _Progresser,
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


def test_getlogpath_supports_missing_file_to_unlink(test_log_dir, monkeypatch):
    """It's ok if the file to unlink was previously removed."""
    monkeypatch.setattr(messages, "_MAX_LOG_FILES", 3)
    previous_fpaths = []
    for _ in range(3):
        fpath = _get_log_filepath("testapp")
        fpath.touch()
        previous_fpaths.append(fpath)
        time.sleep(0.01)  # sleep a little so different log files have different timestamps

    # hook a MITM function to remove the file before it was unlinked
    orig_method = pathlib.Path.unlink

    def mitm(self, *a, **k):
        if self.name.startswith("testapp") and self.name.endswith(".log"):
            # it's trying to remove the log file, let's remove it first
            orig_method(self)
        orig_method(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "unlink", mitm)

    # exercise the code
    _get_log_filepath("testapp")


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
    ephemeral = True
    use_timestamp = True
    with _Progresser(
        fake_printer,
        total,
        text,
        stream,
        delta=False,
        ephemeral_context=ephemeral,
        use_timestamp=use_timestamp,
    ) as progresser:
        progresser.advance(20)
        progresser.advance(30.0)

    assert fake_printer.mock_calls == [
        call.show(stream, "test text (--->)", ephemeral=ephemeral, use_timestamp=use_timestamp),
        call.progress_bar(stream, text, progress=20, total=total, use_timestamp=use_timestamp),
        call.progress_bar(stream, text, progress=30.0, total=total, use_timestamp=use_timestamp),
        call.show(stream, "test text (<---)", ephemeral=ephemeral, use_timestamp=use_timestamp),
    ]


def test_progresser_delta_mode():
    """Just use _Progresser as a context manager in delta mode."""
    stream = sys.stdout
    text = "test text"
    total = 123
    fake_printer = MagicMock()
    ephemeral = True
    use_timestamp = True
    with _Progresser(
        fake_printer,
        total,
        text,
        stream,
        delta=True,
        ephemeral_context=ephemeral,
        use_timestamp=use_timestamp,
    ) as progresser:
        progresser.advance(20.5)
        progresser.advance(30)

    assert fake_printer.mock_calls == [
        call.show(stream, "test text (--->)", ephemeral=ephemeral, use_timestamp=use_timestamp),
        call.progress_bar(stream, text, progress=20.5, total=total, use_timestamp=use_timestamp),
        call.progress_bar(stream, text, progress=50.5, total=total, use_timestamp=use_timestamp),
        call.show(stream, "test text (<---)", ephemeral=ephemeral, use_timestamp=use_timestamp),
    ]


@pytest.mark.parametrize("delta", [False, True])
def test_progresser_negative_values(delta):
    """The progress cannot be negative."""
    fake_printer = MagicMock()
    with _Progresser(fake_printer, 123, "test text", sys.stdout, delta, True, True) as progresser:
        with pytest.raises(ValueError, match="The advance amount cannot be negative"):
            progresser.advance(-1)


def test_progresser_dont_consume_exceptions():
    """It lets the exceptions go through."""
    fake_printer = MagicMock()
    with pytest.raises(ValueError):
        with _Progresser(fake_printer, 123, "test text", sys.stdout, True, True, True):
            raise ValueError()


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
    handler.mode = EmitterMode.VERBOSE
    logging.getLogger().error("test message %s", 23)

    assert handler.printer.mock_calls == [
        call.show(sys.stderr, "test message 23", use_timestamp=False, ephemeral=False),
    ]


def test_handler_emit_quiet(handler):
    """Check emit behaviour in QUIET mode."""
    handler.mode = EmitterMode.QUIET

    logger = logging.getLogger()
    logger.error("test error")
    logger.warning("test warning")
    logger.info("test info")
    logger.debug("test debug")
    logger.log(5, "test custom sub-debug")

    assert handler.printer.mock_calls == [
        call.show(None, "test error", use_timestamp=False, ephemeral=False),
        call.show(None, "test warning", use_timestamp=False, ephemeral=False),
        call.show(None, "test info", use_timestamp=False, ephemeral=False),
        call.show(None, "test debug", use_timestamp=False, ephemeral=False),
    ]


def test_handler_emit_brief(handler):
    """Check emit behaviour in BRIEF mode."""
    handler.mode = EmitterMode.BRIEF

    logger = logging.getLogger()
    logger.error("test error")
    logger.warning("test warning")
    logger.info("test info")
    logger.debug("test debug")
    logger.log(5, "test custom sub-debug")

    assert handler.printer.mock_calls == [
        call.show(None, "test error", use_timestamp=False, ephemeral=False),
        call.show(None, "test warning", use_timestamp=False, ephemeral=False),
        call.show(None, "test info", use_timestamp=False, ephemeral=False),
        call.show(None, "test debug", use_timestamp=False, ephemeral=False),
    ]


def test_handler_emit_verbose(handler):
    """Check emit behaviour in VERBOSE mode."""
    handler.mode = EmitterMode.VERBOSE

    logger = logging.getLogger()
    logger.error("test error")
    logger.warning("test warning")
    logger.info("test info")
    logger.debug("test debug")
    logger.log(5, "test custom sub-debug")

    assert handler.printer.mock_calls == [
        call.show(sys.stderr, "test error", use_timestamp=False, ephemeral=False),
        call.show(sys.stderr, "test warning", use_timestamp=False, ephemeral=False),
        call.show(sys.stderr, "test info", use_timestamp=False, ephemeral=False),
        call.show(None, "test debug", use_timestamp=False, ephemeral=False),
    ]


def test_handler_emit_debug(handler):
    """Check emit behaviour in DEBUG mode."""
    handler.mode = EmitterMode.DEBUG

    logger = logging.getLogger()
    logger.error("test error")
    logger.warning("test warning")
    logger.info("test info")
    logger.debug("test debug")
    logger.log(5, "test custom sub-debug")

    assert handler.printer.mock_calls == [
        call.show(sys.stderr, "test error", use_timestamp=True, ephemeral=False),
        call.show(sys.stderr, "test warning", use_timestamp=True, ephemeral=False),
        call.show(sys.stderr, "test info", use_timestamp=True, ephemeral=False),
        call.show(sys.stderr, "test debug", use_timestamp=True, ephemeral=False),
    ]


def test_handler_emit_trace(handler):
    """Check emit behaviour in TRACE mode."""
    handler.mode = EmitterMode.TRACE

    logger = logging.getLogger()
    logger.error("test error")
    logger.warning("test warning")
    logger.info("test info")
    logger.debug("test debug")
    logger.log(5, "test custom sub-debug")

    assert handler.printer.mock_calls == [
        call.show(sys.stderr, "test error", use_timestamp=True, ephemeral=False),
        call.show(sys.stderr, "test warning", use_timestamp=True, ephemeral=False),
        call.show(sys.stderr, "test info", use_timestamp=True, ephemeral=False),
        call.show(sys.stderr, "test debug", use_timestamp=True, ephemeral=False),
        call.show(sys.stderr, "test custom sub-debug", use_timestamp=True, ephemeral=False),
    ]


# -- tests for the traceback lines extractor


def test_traceback_lines_simple():
    """Extract traceback lines from an exception."""
    try:
        raise ValueError("pumba")
    except ValueError as err:
        tbacklines = list(_get_traceback_lines(err))

    assert tbacklines[0] == "Traceback (most recent call last):"
    assert tbacklines[1].startswith("  File ")
    assert tbacklines[1].endswith(", in test_traceback_lines_simple")
    assert tbacklines[2] == '    raise ValueError("pumba")'
    assert tbacklines[3] == "ValueError: pumba"
