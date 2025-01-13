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
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Union, cast

if TYPE_CHECKING:
    from collections.abc import Collection, MutableSequence
    from typing import Dict, Tuple

import jinja2
import pydantic
from typing_extensions import Self

import craft_cli

TEMPLATE_PATH = "bash_completion.sh.j2"


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


def _get_set_flags(flags: enum.Flag) -> List[enum.Flag]:
    return [f for f in flags.__class__ if f & flags == f]


@dataclasses.dataclass
class CompGen:
    """An object that, when converted to a string, generates a compgen command.

    Excludes '-C' and '-F' options, since they can just as easily be replaced
    with $(...)
    """

    options: Optional[Option] = None
    actions: Optional[Action] = None
    glob_pattern: Optional[str] = None
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    words: List[str] = dataclasses.field(default_factory=list)
    filter_pattern: Optional[str] = None

    def __str__(self) -> str:
        """Represent as a bash completion script."""
        cmd = ["compgen"]
        if self.options:
            for option in _get_set_flags(self.options):
                cmd.extend(["-o", cast(str, option.name)])
        if self.actions:
            for action in _get_set_flags(self.actions):
                cmd.extend(["-A", cast(str, action.name)])
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

    flags: List[str]
    completion_command: Union[str, CompGen]

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
        """Convert an argparse Action into an OptionArgument for parsing."""
        if action.choices:
            completion_command = CompGen(words=list(action.choices))
        elif action.type == pydantic.DirectoryPath:
            completion_command = CompGen(actions=Action.directory)
        elif action.type == pydantic.FilePath:
            completion_command = CompGen(actions=Action.file)
        else:
            completion_command = CompGen()

        return cls(flags=cast(List[str], action.option_strings), completion_command=completion_command)


def complete(shell_cmd: str, get_dispatcher: Callable[[], craft_cli.Dispatcher]) -> str:
    """Generate a bash completion script based on a craft-cli dispatcher.

    :param shell_cmd: The name of the command being completed for
    :param get_dispatcher: A function that returns a populated craft-cli dispatcher
    :return: A bash completion script for ``shell_cmd``
    """
    dispatcher = get_dispatcher()
    env = jinja2.Environment(
        trim_blocks=True,
        lstrip_blocks=True,
        comment_start_string="#{",
        comment_end_string="#}",
        loader=jinja2.FileSystemLoader(Path(__file__).parent),
        autoescape=jinja2.select_autoescape(),
    )
    template = env.get_template(TEMPLATE_PATH)

    command_map: Dict[str, Tuple[Collection[OptionArgument], Collection[OptionArgument], CompGen]] = {}
    for name, cmd_cls in dispatcher.commands.items():
        parser = argparse.ArgumentParser()
        cmd = cmd_cls(None)
        cmd.fill_parser(parser)  # type: ignore[arg-type]
        # reason: for this module, we don't need the help/error
        # capabilities of _CustomArgumentParser
        actions = parser._actions

        options: MutableSequence[OptionArgument] = []
        args: MutableSequence[OptionArgument] = []
        for action in actions:
            opt_arg = OptionArgument.from_action(action)
            if action.option_strings:
                args.append(opt_arg)
                if action.const is None:
                    options.append(opt_arg)

        param_actions = Action(0)
        action_types = {action.type for action in actions if not action.option_strings}
        if pydantic.DirectoryPath in action_types:
            param_actions |= Action.directory
        if Path in action_types or pydantic.FilePath in action_types:
            param_actions |= Action.file

        parameters = CompGen(actions=param_actions, options=Option.bashdefault)
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


def _validate_dispatch_func(raw_ref: str) -> Callable[[], craft_cli.Dispatcher]:
    if len(split := raw_ref.split(":", maxsplit=1)) != 2: # noqa: PLR2004 (no magic values)
        print("aah!")
        raise ValueError

    filepath, func_name = split
    mod_path = Path(filepath).resolve()

    # Add the parent folder of the given module to the import path if needed
    mod_search_dir = str(mod_path.parent)
    if mod_search_dir not in sys.path:
        sys.path.append(mod_search_dir)
    # Then import it
    module = importlib.import_module(mod_path.with_suffix("").name)

    # Type-checking function signatures is impossible without enforcing the
    # function at `func_name` being type-annotated. This is Python though,
    # so just trust that it's a valid function.
    return cast(Callable[[], craft_cli.Dispatcher], getattr(module, func_name))


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
        "func",
        type=_validate_dispatch_func,
        metavar="FUNC_REF",
        help="A reference to a Python function to be imported. The function should take no arguments and return a craft-cli dispatcher.\n"
        "Example: /some/python/file.py:get_dispatcher",
    )
    args = parser.parse_args(sys.argv[1:])

    print(complete(args.shell_cmd, args.func))
