# Copyright 2024 Canonical Ltd.
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

from pathlib import Path

import craft_cli
from craft_cli.completion import complete
from typing import Any, Tuple, Dict, Sequence, Callable, Type

from unittest.mock import patch

class FakeLsCommand(craft_cli.BaseCommand):
    """A copycat ls command."""

    name = "ls"
    help_msg = "Simulate ls"
    overview = "Simulates ls"

    def fill_parser(self, parser: craft_cli.dispatcher._CustomArgumentParser) -> None:
        """Fill out an argument parser with ls args."""
        parser.add_argument("-a", "--all", action="store_true", help="Output all hidden files")
        parser.add_argument(
            "--color", choices=["always", "auto", "never"], help="When to output in color"
        )
        parser.add_argument("path", nargs="*", type=Path, help="Path to list")


class FakeCpCommand(craft_cli.BaseCommand):
    """A copycat cp command."""

    name = "cp"
    help_msg = "cp"
    overview = "cp"

    def fill_parser(self, parser: craft_cli.dispatcher._CustomArgumentParser) -> None:
        """Fill out an argument parser with cp args."""
        parser.add_argument("src", type=Path)
        parser.add_argument("dest", type=Path)

def get_app_info_func(commands: Sequence[Type[craft_cli.BaseCommand]], config: Dict[str, Any] = {}) -> Callable[[], Tuple[craft_cli.Dispatcher, Dict[str, Any]]]:
    basic_group = craft_cli.CommandGroup("basic", commands)

    def _inner() -> Tuple[craft_cli.Dispatcher, Dict[str, Any]]:
        return craft_cli.Dispatcher(
            appname="pybash",
            commands_groups=[basic_group],
            extra_global_args=[],
        ), config

    return _inner

def test_completion_output() -> None:
    app_info_func = get_app_info_func([FakeLsCommand, FakeCpCommand])
    actual_output = complete("testcraft", app_info_func)

    expected_output = (Path(__file__).parent / "test_completion" / "expected_script.sh").read_text()

    assert actual_output == expected_output

def test_app_config_used() -> None:
    app_info_func = get_app_info_func([FakeCpCommand], config={"hello": "world"})

    with patch(__name__ + ".FakeCpCommand.__init__", return_value=None) as complete_mock:
        complete("testcraft", app_info_func)

    complete_mock.assert_called_once_with({"hello": "world"})
