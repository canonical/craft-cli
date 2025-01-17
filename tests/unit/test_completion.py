# Copyright 2025 Canonical Ltd.
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

"""Completion auto-gen unit tests"""

import argparse
from craft_cli import GlobalArgument
from craft_cli.completion.completion import Action, Arg, Option, Argument, CompGen, get_set_flags, CommandMapping
from overrides import override
from typing import List, Dict, Any

import pytest


@pytest.mark.parametrize(
    "input, expected",
    [
        pytest.param(Action(0), [], id="no-flags"),
        pytest.param(Action.alias, [Action.alias], id="one-flag"),
        pytest.param(
            Action.alias | Action.arrayvar | Action.binding,
            [Action.alias, Action.arrayvar, Action.binding],
            id="many-flags",
        ),
    ],
)
def test_get_set_flags(input: Action, expected: List[Action]) -> None:
    assert get_set_flags(input) == expected


@pytest.mark.parametrize(
    "input, expected",
    [
        pytest.param({}, "compgen", id="no-args"),
        pytest.param(
            {
                "options": Option.bashdefault,
            },
            "compgen -o bashdefault",
            id="one-opt",
        ),
        pytest.param(
            {"options": Option.bashdefault | Option.default | Option.dirnames},
            "compgen -o bashdefault -o default -o dirnames",
            id="many-opts",
        ),
        pytest.param(
            {
                "options": Option.bashdefault,
                "glob_pattern": ".*",
            },
            "compgen -o bashdefault -G '.*'",
            id="opt-and-flag",
        ),
        pytest.param(
            {
                "options": Option.bashdefault | Option.default,
                "actions": Action.builtin | Action.file | Action.export,
                "glob_pattern": "*.py*",
                "prefix": "py",
                "suffix": "thon",
                "words": ["one", "two", "three"],
                "filter_pattern": "*.pyc",
            },
            "compgen -o bashdefault -o default -A builtin -A export -A file -G '*.py*' -P py -S thon -W 'one two three' -X '*.pyc'",
            id="all-args",
        ),
    ],
)
def test_compgen(input: Dict[str, Any], expected: str) -> None:
    compgen = CompGen(**input)
    assert str(compgen) == expected


class FakeArg(Arg):
    """Fake argument class to test the the functionality of the Arg ABC"""

    @property
    @override
    def flag_list(self) -> str:
        return ",".join(self.flags)


def test_arg_from_global() -> None:
    global_arg = GlobalArgument(
        "--verbosity",
        "option",
        short_option="-v",
        long_option="--verbosity",
        help_message="",
        choices=["whispering", "yelling"],
        validator=str,
    )
    arg = FakeArg.from_global_argument(global_arg)

    assert arg.flag_list == "--verbosity,-v"
    assert str(arg.completion_command) == "compgen -W 'whispering yelling'"


def test_arg_from_action() -> None:
    action = argparse.Action(["--verbosity", "-v"], "verbosity", choices=["whispering", "yelling"])
    arg = FakeArg.from_action(action)

    assert arg.flag_list == "--verbosity,-v"
    assert str(arg.completion_command) == "compgen -W 'whispering yelling'"


@pytest.mark.parametrize(
    "args, expected_args",
    [
        pytest.param(
            [Argument(["--foo"], completion_command="")],
            "--foo",
            id="one-arg",
        ),
        pytest.param(
            [Argument(["--foo", "--bar", "--baz"], completion_command="")],
            "--foo --bar --baz",
            id="many-args",
        ),
    ],
)
def test_commandmapping_all_args(args: List[Argument], expected_args) -> None:
    mapping = CommandMapping(options=[], args=args, params="")

    assert mapping.all_args == expected_args
