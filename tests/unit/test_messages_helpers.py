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
from unittest.mock import MagicMock, call

import appdirs
import pytest

from craft_cli import messages
from craft_cli.messages import _get_log_filepath, _Progresser

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
