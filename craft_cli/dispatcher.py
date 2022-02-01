# Copyright 2021-2022 Canonical Ltd.
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

"""Argument processing and command dispatching functionality."""

import argparse
import difflib
from collections import namedtuple
from typing import Any, Dict, List, Optional, Tuple, Type

from craft_cli import EmitterMode, emit
from craft_cli.errors import ArgumentParsingError, ProvideHelpException
from craft_cli.helptexts import HelpBuilder

CommandGroup = namedtuple("CommandGroup", "name commands")
"""Definition of a command group.

A list of these is what is passed to the ``Dispatcher`` to run commands as part
of the application.

:param name: identifier of the command group (to be used in help texts).
:param commands: a list of the commands in this group.
"""

GlobalArgument = namedtuple("GlobalArgument", "name type short_option long_option help_message")
"""Definition of a global argument to be handled by the Dispatcher.

:param name: identifier of the argument (the reference in the dictionary returned
    by ``Dispatcher.pre_parse_args`` method)
:param type: the argument type: ``flag`` for arguments that are set to ``True`` if
    specified (``False`` by default), or ``option`` if a value is needed after it.
:param short_option: the short form of the argument (a dash with a letter, e.g. ``-s``).
:param long_option: the long form of the argument (two dashes and a name, e.g. ``--secure``).
:param help_message: the one-line text that describes the argument, for building the help texts.
"""
_DEFAULT_GLOBAL_ARGS = [
    GlobalArgument(
        "help",
        "flag",
        "-h",
        "--help",
        "Show this help message and exit",
    ),
    GlobalArgument(
        "verbose",
        "flag",
        "-v",
        "--verbose",
        "Show debug information and be more verbose",
    ),
    GlobalArgument(
        "quiet",
        "flag",
        "-q",
        "--quiet",
        "Only show warnings and errors, not progress",
    ),
    GlobalArgument(
        "trace",
        "flag",
        "-t",
        "--trace",
        "Show all information needed to trace internal behaviour",
    ),
]


class BaseCommand:
    """Base class to build application commands.

    Subclass this to create a new command; the subclass must define the following attributes:

    - name: the identifier in the command line

    - help_msg: a one line help for user documentation

    - overview: a longer multi-line text with the whole command description

    Also it may override the following one to change its default:

    - common: if it's a common/starter command, which are prioritized in the help (default to
      False)

    It also must/can override some methods for the proper command behaviour (see each
    method's docstring).

    The subclass must be declared in the corresponding section of command groups indicated
    to the Dispatcher.
    """

    common = False
    name: Optional[str] = None
    help_msg: Optional[str] = None
    overview: Optional[str] = None

    def __init__(self, config: Optional[Dict[str, Any]]):
        self.config = config

        # validate attributes
        mandatory = ("name", "help_msg", "overview")
        for attr_name in mandatory:
            if getattr(self, attr_name) is None:
                raise ValueError(f"Bad command configuration: missing value in '{attr_name}'.")

    def fill_parser(self, parser: "_CustomArgumentParser") -> None:
        """Specify command's specific parameters.

        Each command parameters are independent of other commands, but note there are some
        global ones (see `main.Dispatcher._build_argument_parser`).

        If this method is not overridden, the command will not have any parameters.
        """

    def run(self, parsed_args: argparse.Namespace) -> Optional[int]:
        """Execute command's actual functionality.

        It must be overridden by the command implementation.

        This will receive parsed arguments that were defined in :meth:.fill_parser.

        It should return None or the desired process' return code.
        """
        raise NotImplementedError()


class _CustomArgumentParser(argparse.ArgumentParser):
    """ArgumentParser with custom error manager.."""

    def __init__(self, help_builder, *args, **kwargs):
        self._help_builder = help_builder
        super().__init__(*args, **kwargs)

    def error(self, message: str):
        """Show the usage, the error message, and no more."""
        full_msg = self._help_builder.get_usage_message(message, command=self.prog)
        raise ArgumentParsingError(full_msg)


def _get_commands_info(commands_groups: List[CommandGroup]) -> Dict[str, Type[BaseCommand]]:
    """Process the commands groups structure for easier programmatic access."""
    commands: Dict[str, Type[BaseCommand]] = {}
    for command_group in commands_groups:
        for _cmd_class in command_group.commands:
            if _cmd_class.name in commands:
                _stored_class = commands[_cmd_class.name]
                raise RuntimeError(
                    "Multiple commands with same name: "
                    f"{_cmd_class.__name__} and {_stored_class.__name__}"
                )
            commands[_cmd_class.name] = _cmd_class
    return commands


class Dispatcher:  # pylint: disable=too-many-instance-attributes
    """Set up infrastructure and let the needed command run.

    ♪♫"Leeeeeet, the command ruuun"♪♫ https://www.youtube.com/watch?v=cv-0mmVnxPA

    :param appname: the name of the application
    :param commands_groups: a list of command groups available to the user
    :param summary: the summary of the application (for help texts)
    :param extra_global_args: other automatic global arguments than the ones
        provided automatically
    :param default_command: the command to run if none was specified in the command line
    """

    def __init__(
        self,
        appname: str,
        commands_groups: List[CommandGroup],
        *,
        summary: str = "",
        extra_global_args: Optional[List[GlobalArgument]] = None,
        default_command: Optional[Type[BaseCommand]] = None,
    ):
        self._default_command = default_command
        self._help_builder = HelpBuilder(appname, summary, commands_groups)

        self.global_arguments = _DEFAULT_GLOBAL_ARGS[:]
        if extra_global_args is not None:
            self.global_arguments.extend(extra_global_args)

        self.commands = _get_commands_info(commands_groups)
        self._command_class: Optional[Type[BaseCommand]] = None
        self._command_args: Optional[List[str]] = None
        self._loaded_command: Optional[BaseCommand] = None
        self._parsed_command_args: Optional[argparse.Namespace] = None

    def load_command(self, app_config: Any) -> BaseCommand:
        """Load a command."""
        if self._command_class is None:
            raise RuntimeError(
                "Need to parse arguments (call 'pre_parse_args') before loading the command."
            )
        self._loaded_command = self._command_class(app_config)

        # load and parse the command specific options/params
        parser = _CustomArgumentParser(self._help_builder, prog=self._loaded_command.name)
        self._loaded_command.fill_parser(parser)
        self._parsed_command_args = parser.parse_args(self._command_args)
        emit.trace(f"Command parsed sysargs: {self._parsed_command_args}")
        return self._loaded_command

    def _get_global_options(self) -> List[Tuple[str, str]]:
        """Return the global flags ready to present in the help messages as options."""
        options = []
        for arg in self.global_arguments:
            options.append((f"{arg.short_option}, {arg.long_option}", arg.help_message))
        return options

    def _get_general_help(self, *, detailed):
        """Produce the general application help."""
        options = self._get_global_options()
        if detailed:
            help_text = self._help_builder.get_detailed_help(options)
        else:
            help_text = self._help_builder.get_full_help(options)
        return help_text

    def _get_requested_help(self, parameters):
        """Produce the requested help depending on the rest of the command line params."""
        if len(parameters) == 0:
            # provide a general text when help was requested without parameters
            return self._get_general_help(detailed=False)
        if len(parameters) > 1:
            # too many parameters: provide a specific guiding error
            msg = (
                "Too many parameters when requesting help; "
                "pass a command, '--all', or leave it empty"
            )
            text = self._help_builder.get_usage_message(msg)
            raise ArgumentParsingError(text)

        # special parameter to get detailed help
        (param,) = parameters
        if param == "--all":
            # provide a detailed general help when this specific option was included
            return self._get_general_help(detailed=True)

        # at this point the parameter should be a command
        try:
            cmd_class = self.commands[param]
        except KeyError:
            msg = f"command {param!r} not found to provide help for"
            text = self._help_builder.get_usage_message(msg)
            raise ArgumentParsingError(text)  # pylint: disable=raise-missing-from

        # instantiate the command and fill its arguments
        command = cmd_class(None)
        parser = _CustomArgumentParser(self._help_builder, prog=command.name, add_help=False)
        command.fill_parser(parser)

        # produce the complete help message for the command
        options = self._get_global_options()
        for action in parser._actions:  # pylint: disable=protected-access
            # store the different options if present, otherwise it's just the dest
            help_text = "" if action.help is None else action.help
            if action.option_strings:
                options.append((", ".join(action.option_strings), help_text))
            else:
                if action.metavar is None:
                    dest = action.dest
                else:
                    assert isinstance(action.metavar, str)  # may be a tuple, but only for options
                    dest = action.metavar
                options.append((dest, help_text))

        help_text = self._help_builder.get_command_help(command, options)
        return help_text

    def _build_no_command_error(self, missing_command: str) -> str:
        """Build the error help text for missing command, providing options."""
        all_alternatives = self.commands.keys()
        similar = difflib.get_close_matches(missing_command, all_alternatives)
        if len(similar) == 0:
            extra_similar = ""
        else:
            if len(similar) == 1:
                similar_text = repr(similar[0])
            else:
                *previous, last = similar
                similar_text = ", ".join(repr(x) for x in previous) + f" or {last!r}"
            extra_similar = f", maybe you meant {similar_text}"
        msg = f"no such command {missing_command!r}{extra_similar}"
        return self._help_builder.get_usage_message(msg)

    def pre_parse_args(
        self, sysargs: List[str]
    ):  # pylint: disable=too-many-branches disable=too-many-statements
        """Pre-parse sys args.

        Several steps:

        - extract the global options and detects the possible command and its args

        - validate global options and apply them

        - validate that command is correct (NOT loading and parsing its arguments)
        """
        # get all arguments (default to what's specified) and those per options, to filter sysargs
        global_args: Dict[str, Any] = {}
        arg_per_option = {}
        options_with_equal = []
        for arg in self.global_arguments:
            arg_per_option[arg.short_option] = arg
            arg_per_option[arg.long_option] = arg
            if arg.type == "flag":
                global_args[arg.name] = False
            elif arg.type == "option":
                global_args[arg.name] = None
                options_with_equal.append(arg.long_option + "=")
            else:
                raise ValueError("Bad global args structure.")

        filtered_sysargs = []
        sysargs_it = iter(sysargs)
        for sysarg in sysargs_it:
            if sysarg in arg_per_option:
                arg = arg_per_option[sysarg]
                if arg.type == "flag":
                    global_args[arg.name] = True
                else:
                    try:
                        global_args[arg.name] = next(sysargs_it)
                    except StopIteration:
                        raise ArgumentParsingError(  # pylint: disable=raise-missing-from
                            f"The {arg.name!r} option expects one argument."
                        )
            elif sysarg.startswith(tuple(options_with_equal)):
                option, value = sysarg.split("=", 1)
                arg = arg_per_option[option]
                if not value:
                    raise ArgumentParsingError(f"The {arg.name!r} option expects one argument.")
                global_args[arg.name] = value
            else:
                filtered_sysargs.append(sysarg)

        # control and use quiet/verbose options
        if sum([global_args[key] for key in ("quiet", "verbose", "trace")]) > 1:
            raise ArgumentParsingError(
                "The 'verbose', 'trace' and 'quiet' options are mutually exclusive."
            )
        if global_args["quiet"]:
            emit.set_mode(EmitterMode.QUIET)
        elif global_args["verbose"]:
            emit.set_mode(EmitterMode.VERBOSE)
        elif global_args["trace"]:
            emit.set_mode(EmitterMode.TRACE)
        emit.trace(f"Raw pre-parsed sysargs: args={global_args} filtered={filtered_sysargs}")

        # handle requested help through -h/--help options
        if global_args["help"]:
            help_text = self._get_requested_help(filtered_sysargs)
            raise ProvideHelpException(help_text)

        if not filtered_sysargs or filtered_sysargs[0].startswith("-"):
            # no args or start with an option: trigger a default command, if any
            if self._default_command is None:
                help_text = self._get_general_help(detailed=False)
                raise ArgumentParsingError(help_text)
            emit.trace(f"Using default command: {self._default_command.name!r}")
            assert self._default_command.name is not None  # validated by BaseCommand
            filtered_sysargs.insert(0, self._default_command.name)

        command = filtered_sysargs[0]
        cmd_args = filtered_sysargs[1:]

        # handle requested help through implicit "help" command
        if command == "help":
            help_text = self._get_requested_help(cmd_args)
            raise ProvideHelpException(help_text)

        self._command_args = cmd_args
        try:
            self._command_class = self.commands[command]
        except KeyError:
            help_text = self._build_no_command_error(command)
            raise ArgumentParsingError(help_text)  # pylint: disable=raise-missing-from

        emit.trace(f"General parsed sysargs: command={ command!r} args={cmd_args}")
        return global_args

    def run(self) -> Optional[int]:
        """Really run the command."""
        if self._loaded_command is None:
            raise RuntimeError("Need to load the command (call 'load_command') before running it.")
        assert self._parsed_command_args is not None
        return self._loaded_command.run(self._parsed_command_args)
