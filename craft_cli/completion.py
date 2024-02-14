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
import pathlib
import shlex
from collections.abc import Collection
from typing import Sequence

import jinja2
import pydantic
from typing_extensions import Self

import craft_cli


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


@dataclasses.dataclass(kw_only=True, slots=True)
class CompGen:
    """An object that, when converted to a string, generates a compgen command.

    Excludes '-C' and '-F' options, since they can just as easily be replaced with $(...)
    """

    options: None | Option = None
    actions: None | Action = None
    glob_pattern: str | None = None
    prefix: str | None = None
    suffix: str | None = None
    words: Collection[str] = ()
    filter_pattern: str | None = None

    def __str__(self):
        cmd = ["compgen"]
        if self.options:
            for option in self.options:
                cmd.extend(["-o", option.name])
        if self.actions:
            for action in self.actions:
                cmd.extend(["-A", action.name])
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
class OptionArgument:
    """An argument that's an option."""
    flags: Sequence[str]
    completion_command: str | CompGen

    @classmethod
    def from_global_argument(cls, argument: craft_cli.GlobalArgument) -> Self:
        """Convert a general GlobalArgument to an OptionArgument for parsing."""
        if argument.short_option:
            flags = [argument.long_option, argument.short_option]
        else:
            flags = [argument.long_option]
        if argument.choices:
            completion_command = CompGen(words=argument.choices)
        elif argument.validator == pydantic.DirectoryPath:
            completion_command = CompGen(actions=Action.directory)
        elif argument.validator == pydantic.FilePath:
            completion_command = CompGen(actions=Action.file)
        else:
            completion_command = CompGen()
        return cls(flags=flags, completion_command=completion_command)

    @classmethod
    def from_action(cls, action: argparse.Action) -> Self:
        """Convert an argparse Action into an OptionArgument."""
        if action.choices:
            completion_command = CompGen(words=list(action.choices))
        elif action.type == pydantic.DirectoryPath:
            completion_command = CompGen(actions=Action.directory)
        elif action.type == pydantic.FilePath:
            completion_command = CompGen(actions=Action.file)
        else:
            completion_command = CompGen(options=Option.bashdefault)

        return cls(
            flags=action.option_strings,
            completion_command=completion_command
        )


def complete(shell_cmd: str, dispatcher: craft_cli.Dispatcher):
    """Write out a completion script for the given dispatcher."""
    env = jinja2.Environment(
        trim_blocks=True,
        lstrip_blocks=True,
        comment_start_string="#{",
        comment_end_string="#}",
        loader=jinja2.FileSystemLoader(pathlib.Path(__file__).parent),
    )
    template = env.get_template("bash_completion.j2.sh")

    command_map: dict[str, tuple[list[OptionArgument], list[OptionArgument], CompGen]] = {}
    for name, cmd_cls in dispatcher.commands.items():
        parser = argparse.ArgumentParser()
        cmd = cmd_cls(None)
        cmd.fill_parser(parser)
        actions = parser._actions
        options = [
            OptionArgument.from_action(action)
            for action in actions
            if action.const is None and action.option_strings
        ]
        args = [
            OptionArgument.from_action(action)
            for action in actions
            if action.option_strings
        ]
        param_actions = Action(0)
        action_types = {action.type for action in actions if not action.option_strings}
        if pydantic.DirectoryPath in action_types:
            param_actions |= Action.directory
        if pydantic.FilePath in action_types or pathlib.Path in action_types:
            param_actions |= Action.file
        parameters = CompGen(
            actions=param_actions,
            options=Option.bashdefault,
        )
        command_map[name] = options, args, parameters


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
