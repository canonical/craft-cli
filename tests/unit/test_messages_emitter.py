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

"""Tests that check the whole Emitter machinery."""

import sys
from unittest.mock import call, patch

import pytest

from craft_cli.messages import Emitter, EmitterMode


class RecordingEmitter(Emitter):
    """Class to cheat pyright.

    Otherwise it complains I'm setting printer_class to Emitter.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.printer_calls = []


@pytest.fixture
def get_initiated_emitter():
    """Provide an initiated Emitter ready to test.

    It has a patched "printer" and an easy way to test its calls (after it was initiated).

    It's used almost in all tests (except those that test the init call).
    """
    with patch("craft_cli.messages._Printer", autospec=True) as mock_printer:

        def func(mode, greeting="default greeting"):
            emitter = RecordingEmitter()
            emitter.init(mode, greeting)
            emitter.printer_calls = mock_printer.mock_calls
            emitter.printer_calls.clear()
            return emitter

        yield func


# -- tests for init and setting mode


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_init_quietish(mode):
    """Init the class in some quiet-ish mode."""
    greeting = "greeting"
    emitter = Emitter()
    with patch("craft_cli.messages._Printer") as mock_printer:
        emitter.init(mode, greeting)

    assert emitter.mode == mode
    assert mock_printer.mock_calls == [
        call(),  # the _Printer instantiation
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_init_verboseish(mode):
    """Init the class in some verbose-ish mode."""
    greeting = "greeting"
    emitter = Emitter()
    with patch("craft_cli.messages._Printer") as mock_printer:
        emitter.init(mode, greeting)

    assert emitter.mode == mode
    assert mock_printer.mock_calls == [
        call(),  # the _Printer instantiation
        call().show(sys.stderr, greeting, use_timestamp=True, end_line=True),
    ]


@pytest.mark.parametrize("method_name", ["set_mode", "message", "ended_ok"])
def test_needs_init(method_name):
    """Check that calling other methods needs emitter first to be initiated."""
    emitter = Emitter()
    method = getattr(emitter, method_name)
    with pytest.raises(RuntimeError, match="Emitter needs to be initiated first"):
        method()


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_set_mode_quietish(get_initiated_emitter, mode):
    """Set the class to some quiet-ish mode."""
    greeting = "greeting"
    emitter = get_initiated_emitter(EmitterMode.QUIET, greeting=greeting)
    emitter.set_mode(mode)

    assert emitter.mode == mode
    assert emitter.printer_calls == []


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_set_mode_verboseish(get_initiated_emitter, mode):
    """Set the class to some verbose-ish mode."""
    greeting = "greeting"
    emitter = get_initiated_emitter(EmitterMode.QUIET, greeting=greeting)
    emitter.set_mode(mode)

    assert emitter.mode == mode
    assert emitter.printer_calls == [
        call().show(sys.stderr, greeting, use_timestamp=True, end_line=True),
    ]


# -- tests for emitting messages of all kind


@pytest.mark.parametrize("mode", EmitterMode)  # all modes!
def test_message_final(get_initiated_emitter, mode):
    """Emit a final message."""
    emitter = get_initiated_emitter(mode)
    emitter.message("some text")

    assert emitter.printer_calls == [
        call().show(sys.stdout, "some text", use_timestamp=False),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_message_intermediate_quietish(get_initiated_emitter, mode):
    """Emit an intermediate message when in a quiet-ish mode."""
    emitter = get_initiated_emitter(mode)
    emitter.message("some text", intermediate=True)

    assert emitter.printer_calls == [
        call().show(sys.stdout, "some text", use_timestamp=False),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_message_intermediate_verboseish(get_initiated_emitter, mode):
    """Emit an intermediate message when in a verbose-ish mode."""
    emitter = get_initiated_emitter(mode)
    emitter.message("some text", intermediate=True)

    assert emitter.printer_calls == [
        call().show(sys.stdout, "some text", use_timestamp=True),
    ]


# -- tests for stopping the machinery


def test_ended_ok(get_initiated_emitter):
    """Finish everything."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    emitter.ended_ok()

    assert emitter.printer_calls == [call().stop()]
