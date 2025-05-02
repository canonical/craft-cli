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

"""Complete a fully set-up dispatcher."""

import argparse
import dataclasses
import enum
import importlib
import shlex
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import jinja2
from overrides import override
from typing_extensions import Self

import craft_cli

TEMPLATE_PATH = "bash_completion.sh.j2"

DispatcherAndConfig = tuple[craft_cli.Dispatcher, dict[str, Any] | None]


class Option(enum.Flag):
    """An option flag for compgen."""

    bashdefault = enum.auto()
    default = enum.auto()
    dirnames = enum.auto()
    filenames = enum.auto()
    noquote = enum.auto()
    nosort = enum.auto()
    nospace = enum.auto()
    plusdirs = enum.auto()


class Action(enum.Flag):
    """An action flag for compgen."""

    alias = enum.auto()
    arrayvar = enum.auto()
    binding = enum.auto()
    builtin = enum.auto()
    command = enum.auto()
    directory = enum.auto()
    disabled = enum.auto()
    enabled = enum.auto()
    export = enum.auto()
    file = enum.auto()
    function = enum.auto()
    group = enum.auto()
    helptopic = enum.auto()
    hostname = enum.auto()
    job = enum.auto()
    keyword = enum.auto()
    running = enum.auto()
    service = enum.auto()
    setopt = enum.auto()
    shopt = enum.auto()
    signal = enum.auto()
    user = enum.auto()
    variable = enum.auto()


def get_set_flags(flags: enum.Flag) -> list[enum.Flag]:
    """Get a list of the set flags in a flag enum."""
    # Sorted for consistent testing
    return sorted([f for f in flags.__class__ if f & flags == f], key=lambda f: f.value)


@dataclasses.dataclass
class CompGen:
    """An object that, when converted to a string, generates a compgen command.

    Excludes '-C' and '-F' options, since they can just as easily be replaced
    with $(...)
    """

    options: Option | None = None
    actions: Action | None = None
    glob_pattern: str | None = None
    prefix: str | None = None
    suffix: str | None = None
    words: list[str] = dataclasses.field(default_factory=list)
    filter_pattern: str | None = None

    def __str__(self) -> str:
        """Represent as a bash completion script."""
        cmd = ["compgen"]
        if self.options:
            for option in get_set_flags(self.options):
                cmd.extend(["-o", cast("str", option.name)])
        if self.actions:
            for action in get_set_flags(self.actions):
                cmd.extend(["-A", cast("str", action.name)])
        if self.glob_pattern:
            cmd.extend(["-G", self.glob_pattern])
        if self.prefix:
            cmd.extend(["-P", self.prefix])
        if self.suffix:
            cmd.extend(["-S", self.suffix])
        if self.words:
            cmd.extend(["-W", " ".join(self.words)])
        if self.filter_pattern:
            cmd.extend(["-X", self.filter_pattern])

        return shlex.join(cmd)


@dataclasses.dataclass
class Arg(ABC):
    """An argument baseclass."""

    flags: list[str]
    completion_command: str | CompGen

    @classmethod
    def from_global_argument(cls, argument: craft_cli.GlobalArgument) -> Self:
        """Convert a general GlobalArgument to an OptionArgument for parsing."""
        if argument.short_option:
            flags = [argument.long_option, argument.short_option]
        else:
            flags = [argument.long_option]

        completion_command = CompGen(words=argument.choices) if argument.choices else CompGen()

        return cls(flags=flags, completion_command=completion_command)

    @classmethod
    def from_action(cls, action: argparse.Action) -> Self:
        """Convert an argparse Action into an OptionArgument for parsing."""
        completion_command = CompGen(words=list(action.choices)) if action.choices else CompGen()

        return cls(
            flags=cast("list[str]", action.option_strings), completion_command=completion_command
        )

    @property
    @abstractmethod
    def flag_list(self) -> str:
        """A list of all flags associated with this argument."""
        ...


class Argument(Arg):
    """A simple argument."""

    @property
    @override
    def flag_list(self) -> str:
        """A list of all flags associated with this argument."""
        return " ".join(self.flags)


class OptionArgument(Arg):
    """An argument that's an option."""

    @property
    @override
    def flag_list(self) -> str:
        """A list of all flags associated with this argument."""
        return "|".join(self.flags)


@dataclasses.dataclass
class CommandMapping:
    """A utility class containing all arguments for a command."""

    options: list[OptionArgument]
    args: list[Argument]
    params: str | CompGen

    @property
    def all_args(self) -> str:
        """All arguments, joined by spaces."""
        return " ".join([a.flag_list for a in self.args])


def complete(shell_cmd: str, get_app_info: Callable[[], DispatcherAndConfig]) -> str:
    """Generate a bash completion script based on a craft-cli dispatcher.

    :param shell_cmd: The name of the command being completed for
    :param get_app_info: A function that returns a populated craft-cli dispatcher and the config
    needed to create its commands
    :return: A bash completion script for ``shell_cmd``
    """
    dispatcher, app_config = get_app_info()
    env = jinja2.Environment(
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        comment_start_string="#{",
        comment_end_string="#}",
        loader=jinja2.FileSystemLoader(Path(__file__).parent),
        autoescape=jinja2.select_autoescape(),
    )
    template = env.get_template(TEMPLATE_PATH)

    command_map: dict[str, CommandMapping] = {}
    for name, cmd_cls in dispatcher.commands.items():
        parser = argparse.ArgumentParser()
        cmd = cmd_cls(app_config)
        cmd.fill_parser(parser)  # type: ignore[arg-type]
        # reason: for this module, we don't need the help/error
        # capabilities of _CustomArgumentParser
        actions = parser._actions

        options: list[OptionArgument] = []
        args: list[Argument] = []
        for action in actions:
            if action.option_strings:
                args.append(Argument.from_action(action))
                if action.const is None:
                    options.append(OptionArgument.from_action(action))

        param_actions = Action(0)
        action_types = {action.type for action in actions if not action.option_strings}
        if Path in action_types:
            param_actions |= Action.file

        parameters = CompGen(actions=param_actions, options=Option.bashdefault)
        command_map[name] = CommandMapping(list(options), list(args), parameters)

    global_opts = [
        OptionArgument.from_global_argument(arg)
        for arg in dispatcher.global_arguments
        if arg.type == "option"
    ]

    return template.render(
        shell_cmd=shell_cmd,
        commands=command_map,
        global_args=dispatcher.global_arguments,
        global_opts=global_opts,
    )


def _validate_app_info(raw_ref: str) -> Callable[[], DispatcherAndConfig]:
    if len(split := raw_ref.split(":", maxsplit=1)) != 2:  # noqa: PLR2004 (no magic values)
        raise ValueError

    mod_path, func_name = split

    module = importlib.import_module(mod_path)

    # Type-checking function signatures is impossible without enforcing the
    # function at `func_name` being type-annotated. This is Python though,
    # so just trust that it's a valid function.
    return cast(
        "Callable[[], tuple[craft_cli.Dispatcher, dict[str, Any]]]", getattr(module, func_name)
    )


def main() -> None:
    """Entry point for bash completion script generation."""
    parser = argparse.ArgumentParser(
        prog="craft_cli.completion",
        description="Generate bash completion scripts from your craft-cli dispatcher. Only bash and other Bourne-like shells are supported currently.",
    )
    parser.add_argument(
        "shell_cmd",
        type=str,
        metavar="SHELL_CMD",
        help="The name of the binary completion scripts are being generated for.",
    )
    parser.add_argument(
        "app_info",
        type=_validate_app_info,
        metavar="APP_INFO_FUNC",
        help="A reference to a Python function to be imported. The function should take no arguments and return a tuple of (craft-cli dispatcher, app config).\n"
        "Example: some.python.module:get_app_info",
    )
    args = parser.parse_args(sys.argv[1:])

    # Necessary to avoid errors from running foreign functions that use the craft-cli emitter
    craft_cli.emit.init(
        craft_cli.EmitterMode.QUIET, "craft-cli completion", "Generating completion scripts..."
    )

    print(complete(args.shell_cmd, args.app_info))

    craft_cli.emit.ended_ok()
