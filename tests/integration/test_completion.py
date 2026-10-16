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

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import craft_cli
import pytest
from craft_cli.completion import complete
from craft_cli.completion.completion import DispatcherAndConfig


class FakeLsCommand(craft_cli.BaseCommand):
    """A copycat ls command."""

    name = "ls"
    help_msg = "Simulate ls"
    overview = "Simulates ls"

    def fill_parser(self, parser: craft_cli.dispatcher._CustomArgumentParser) -> None:
        """Fill out an argument parser with ls args."""
        parser.add_argument(
            "-a", "--all", action="store_true", help="Output all hidden files"
        )
        parser.add_argument(
            "--color",
            choices=["always", "auto", "never"],
            help="When to output in color",
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


def get_app_info_func(
    commands: list[type[craft_cli.BaseCommand]], config: dict[str, Any] | None = None
) -> Callable[[], DispatcherAndConfig]:
    if config is None:
        config = {}
    basic_group = craft_cli.CommandGroup("basic", commands)

    def _inner() -> DispatcherAndConfig:
        return craft_cli.Dispatcher(
            appname="pybash",
            commands_groups=[basic_group],
            extra_global_args=[],
        ), config

    return _inner


def test_completion_output() -> None:
    shfmt = shutil.which("shfmt")
    if shfmt is None:
        pytest.skip("'shfmt' command is required to normalize shell script formatting")

    app_info_func = get_app_info_func([FakeLsCommand, FakeCpCommand])
    actual_output = complete("testcraft", app_info_func)

    # Normalize the generated script through shfmt before comparing: the
    # fixture file is covered by the repo's shfmt formatting (while the Jinja2
    # template that produces this output is excluded), so both sides must be
    # compared in shfmt-normalized form.
    actual_output = subprocess.run(
        [shfmt, "-i", "2"],
        input=actual_output,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    expected_output = (
        Path(__file__).parent / "test_completion" / "expected_script.sh"
    ).read_text()

    assert actual_output == expected_output


class FakeMvCommand(craft_cli.BaseCommand):
    """A copycat mv command initialized with a dict."""

    name = "mv"
    help_msg = "mv"
    overview = "mv"

    def __init__(self, config: dict[str, Any]) -> None:
        config["testing_was_used_by_init"] = True
        super().__init__(config)


def test_app_config_used() -> None:
    config = {"hello": "world"}
    app_info_func = get_app_info_func([FakeMvCommand], config=config)
    complete("testcraft", app_info_func)
    assert config.get("testing_was_used_by_init")
