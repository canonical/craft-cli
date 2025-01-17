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

import textwrap
from pathlib import Path

import craft_cli
from craft_cli.completion import complete


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

def test_completion() -> None:
    def _get_dispatcher() -> craft_cli.Dispatcher:
        basic_group = craft_cli.CommandGroup("basic", [FakeLsCommand, FakeCpCommand])

        return craft_cli.Dispatcher(
            appname="pybash",
            commands_groups=[basic_group],
            extra_global_args=[],
        )

    actual_output = complete("testcraft", _get_dispatcher)

    expected_output = (Path(__file__).parent / "test_completion" / "expected_script.sh").read_text()

    assert actual_output == expected_output
