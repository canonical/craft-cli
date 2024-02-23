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

from __future__ import annotations

import argparse
import difflib
from typing import Any, Literal, NamedTuple, NoReturn, Optional, Sequence

from craft_cli import EmitterMode, emit
from craft_cli.errors import ArgumentParsingError, ProvideHelpException
from craft_cli.helptexts import HelpBuilder, OutputFormat


class CommandGroup(NamedTuple):
    """Definition of a command group.

    A list of these is what is passed to the ``Dispatcher`` to run commands as part
    of the application.
    """

    name: str
    """The identifier of the command group (to be used in help texts)."""

    commands: Sequence[type[BaseCommand]]
    """A list of the commands belonging in this group."""

    ordered: bool = False
    """Whether the commands in this group are already in the correct order (defaults to False)."""


class GlobalArgument(NamedTuple):
    """Definition of a global argument to be handled by the Dispatcher."""

    name: str
    """Identifier of the argument (the reference in the dictionary returned) by the
      ``Dispatcher.pre_parse_args()`` method)"""

    type: Literal["flag", "option"]
    """The argument type: ``flag`` for arguments that are set to ``True`` if specified
      (``False`` by default), or ``option`` if a value is needed after it."""

    short_option: str | None
    """The short form of the argument (a dash with a letter, e.g. ``-s``); it can be None
      if the option does not have a short form."""

    long_option: str
    """The long form of the argument (two dashes and a name, e.g. ``--secure``)."""

    help_message: str
    """the one-line text that describes the argument, for building the help texts."""


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
        "verbosity",
        "option",
        None,
        "--verbosity",
        "Set the verbosity level to 'quiet', 'brief', 'verbose', 'debug' or 'trace'",
    ),
]


class BaseCommand:
    """Base class to build application commands.

    Subclass this to create a new command; the subclass must define the ``name``,
    ``help_msg``, and ``overview`` attributes. Additionally, it may override the
    ``common`` and ``hidden`` attributes to change from their default values.

    The subclass may also override some methods for the proper command behaviour (see each
    method's docstring).

    Finally, the subclass must be declared in the corresponding section of command groups
    indicated to the Dispatcher.
    """

    name: str
    """The identifier in the command line, like "build" or "pack"."""

    help_msg: str
    """A one-line help message for user documentation."""

    overview: str
    """Longer, multi-line text with the whole command description."""

    common: bool = False
    """Whether this is a common/starter command, which are prioritized in the help
      (defaults to False)."""

    hidden: bool = False
    """Do not show in help texts, useful for aliases or deprecated commands (defaults
      to False)."""

    def __init__(self, config: dict[str, Any] | None) -> None:
        self.config = config

        # validate attributes
        mandatory = ("name", "help_msg", "overview")
        for attr_name in mandatory:
            if getattr(self, attr_name, None) is None:
                raise ValueError(f"Bad command configuration: missing value in '{attr_name}'.")
        if self.common and self.hidden:
            raise ValueError("Common commands can not be hidden.")

    def fill_parser(self, parser: _CustomArgumentParser) -> None:
        """Specify command's specific parameters.

        Each command parameters are independent of other commands, but note there are some
        global ones (see `main.Dispatcher._build_argument_parser`).

        If this method is not overridden, the command will not have any parameters.

        :param parser: The object to fill with this command's parameters.
        """

    # NOTE: run() returns `Optional[int]` instead of `int | None` as the latter would
    # be a breaking change for subclasses that override this with just `None` and
    # use the `overrides.override` decorator. See:
    # https://github.com/mkorpela/overrides/issues/115
    def run(self, parsed_args: argparse.Namespace) -> Optional[int]:  # noqa: UP007
        """Execute command's actual functionality.

        It must be overridden by the command implementation.

        :param parsed_args: The parsed arguments that were defined in :meth:`fill_parser`.
        :return: This method should return ``None`` or the desired process' return code.
        """
        raise NotImplementedError


class _CustomArgumentParser(argparse.ArgumentParser):
    """ArgumentParser with custom error manager."""

    def __init__(
        self,
        help_builder: HelpBuilder,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._help_builder = help_builder
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> NoReturn:
        """Show the usage, the error message, and no more."""
        full_msg = self._help_builder.get_usage_message(message, command=self.prog)
        raise ArgumentParsingError(full_msg)


def _get_commands_info(commands_groups: list[CommandGroup]) -> dict[str, type[BaseCommand]]:
    """Process the commands groups structure for easier programmatic access."""
    commands: dict[str, type[BaseCommand]] = {}
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


class Dispatcher:
    """Set up infrastructure and let the needed command run.

    ♪♫"Leeeeeet, the command ruuun"♪♫ https://www.youtube.com/watch?v=cv-0mmVnxPA

    :param appname: the name of the application
    :param commands_groups: a list of command groups available to the user
    :param summary: the summary of the application (for help texts)
    :param extra_global_args: other automatic global arguments than the ones
        provided automatically
    :param default_command: the command to run if none was specified in the command line
    """

    def __init__(  # noqa: PLR0913 (too many arguments)
        self,
        appname: str,
        commands_groups: list[CommandGroup],
        *,
        summary: str = "",
        extra_global_args: list[GlobalArgument] | None = None,
        default_command: type[BaseCommand] | None = None,
    ) -> None:
        self._default_command = default_command
        self._help_builder = HelpBuilder(appname, summary, commands_groups)

        self.global_arguments = _DEFAULT_GLOBAL_ARGS[:]
        if extra_global_args is not None:
            self.global_arguments.extend(extra_global_args)

        self.commands = _get_commands_info(commands_groups)
        self._command_class: type[BaseCommand] | None = None
        self._command_args: list[str] | None = None
        self._loaded_command: BaseCommand | None = None
        self._parsed_command_args: argparse.Namespace | None = None

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

    def parsed_args(self) -> argparse.Namespace:
        """Get the parsed command-line arguments."""
        if self._parsed_command_args is None:
            raise RuntimeError(
                "Need to load the command (call 'load_command') before retrieving the parsed arguments."
            )
        return self._parsed_command_args

    def _get_global_options(self) -> list[tuple[str, str]]:
        """Return the global flags ready to present in the help messages as options."""
        options = []
        for arg in self.global_arguments:
            if arg.short_option is None:
                indicator = f"{arg.long_option}"
            else:
                indicator = f"{arg.short_option}, {arg.long_option}"
            options.append((indicator, arg.help_message))
        return options

    def _get_general_help(self, *, detailed: bool) -> str:
        """Produce the general application help."""
        options = self._get_global_options()
        if detailed:
            help_text = self._help_builder.get_detailed_help(options)
        else:
            help_text = self._help_builder.get_full_help(options)
        return help_text

    def _build_usage_exc(self, text: str) -> ArgumentParsingError:
        """Build an ArgumentParsingError exception with the usage message from the given text."""
        return ArgumentParsingError(self._help_builder.get_usage_message(text))

    def _get_requested_help(  # noqa: PLR0912 (too many branches)
        self, parameters: list[str]
    ) -> str:
        """Produce the requested help depending on the rest of the command line params."""
        if len(parameters) == 0:
            # provide a general text when help was requested without parameters
            return self._get_general_help(detailed=False)

        argument_definitions = [
            GlobalArgument("all", "flag", None, "--all", ""),
            GlobalArgument("format", "option", None, "--format", ""),
        ]
        options, filtered_params = self._parse_options(argument_definitions, parameters)

        # special parameter to get detailed help
        option_format = options["format"]
        if options["all"] and not option_format:
            # provide a detailed general help when this specific option was included
            if filtered_params:
                raise self._build_usage_exc("The --all option is only allowed alone")
            return self._get_general_help(detailed=True)

        if option_format and not filtered_params:
            msg = "The --format option is allowed only when requesting help for a specific command"
            raise self._build_usage_exc(msg)

        try:
            output_format = OutputFormat[option_format] if option_format else OutputFormat.plain
        except KeyError:
            allowed = (repr(of.name) for of in OutputFormat)
            msg = f"Invalid value for --format; allowed are: {', '.join(sorted(allowed))}"
            raise self._build_usage_exc(msg) from None

        if len(filtered_params) == 1:
            # at this point the remaining parameter should be a command
            cmdname = filtered_params[0]
        else:
            # too many parameters: provide a specific guiding error; note it cannot be empty at
            # this point in the code
            msg = (
                "Too many parameters when requesting help; "
                "pass a command (optionally with --format), '--all', or leave it empty"
            )
            raise self._build_usage_exc(msg)

        try:
            cmd_class = self.commands[cmdname]
        except KeyError:
            msg = f"command {cmdname!r} not found to provide help for"
            raise self._build_usage_exc(msg) from None

        # instantiate the command and fill its arguments
        command = cmd_class(None)
        parser = _CustomArgumentParser(self._help_builder, prog=command.name, add_help=False)
        command.fill_parser(parser)

        # produce the complete help message for the command
        command_options = self._get_global_options()
        for action in parser._actions:
            # store the different options if present, otherwise it's just the dest
            help_text = "" if action.help is None else action.help
            if action.option_strings:
                command_options.append((", ".join(action.option_strings), help_text))
            else:
                if action.metavar is None:
                    dest = action.dest
                else:
                    # may be a tuple, but only for options
                    assert isinstance(action.metavar, str)  # noqa: S101 (use of assert)
                    dest = action.metavar
                command_options.append((dest, help_text))

        return self._help_builder.get_command_help(command, command_options, output_format)

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

    def _parse_options(  # noqa: PLR0912 (too many branches)
        self, defined_arguments: list[GlobalArgument], sysargs: list[str]
    ) -> tuple[dict[str, Any], list[str]]:
        """Parse arguments."""
        # get all arguments (default to what's specified) and those per options, to filter sysargs
        global_args: dict[str, Any] = {}
        arg_per_option = {}
        options_with_equal = []
        for arg in defined_arguments:
            if arg.short_option is not None:
                arg_per_option[arg.short_option] = arg
            arg_per_option[arg.long_option] = arg
            if arg.type == "flag":
                global_args[arg.name] = False
            elif arg.type == "option":
                global_args[arg.name] = None
                options_with_equal.append(arg.long_option + "=")
            else:
                raise ValueError("Bad args structure.")

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
                        msg = f"The {arg.name!r} option expects one argument."
                        raise self._build_usage_exc(msg) from None
            elif sysarg.startswith(tuple(options_with_equal)):
                option, value = sysarg.split("=", 1)
                arg = arg_per_option[option]
                if not value:
                    raise self._build_usage_exc(f"The {arg.name!r} option expects one argument.")
                global_args[arg.name] = value
            else:
                filtered_sysargs.append(sysarg)
        return global_args, filtered_sysargs

    def pre_parse_args(self, sysargs: list[str]) -> dict[str, Any]:
        """Pre-parse sys args.

        Several steps:

        - extract the global options and detects the possible command and its args

        - validate global options and apply them

        - validate that command is correct (NOT loading and parsing its arguments)
        """
        global_args, filtered_sysargs = self._parse_options(self.global_arguments, sysargs)

        # control and use quiet/verbose/verbosity options
        if sum(1 for key in ("quiet", "verbose", "verbosity") if global_args[key]) > 1:
            raise self._build_usage_exc(
                "The 'verbose', 'quiet' and 'verbosity' options are mutually exclusive."
            )
        if global_args["quiet"]:
            emit.set_mode(EmitterMode.QUIET)
        elif global_args["verbose"]:
            emit.set_mode(EmitterMode.VERBOSE)
        elif global_args["verbosity"]:
            try:
                verbosity_level = EmitterMode[global_args["verbosity"].upper()]
            except KeyError:
                raise self._build_usage_exc(
                    "Bad verbosity level; valid values are "
                    "'quiet', 'brief', 'verbose', 'debug' and 'trace'."
                ) from None
            emit.set_mode(verbosity_level)
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
            # validated by BaseCommand
            assert self._default_command.name is not None  # noqa: S101 (use of assert)
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
            raise ArgumentParsingError(help_text) from None

        emit.trace(f"General parsed sysargs: command={ command!r} args={cmd_args}")
        return global_args

    def run(self) -> int | None:
        """Really run the command."""
        if self._loaded_command is None:
            raise RuntimeError("Need to load the command (call 'load_command') before running it.")
        assert self._parsed_command_args is not None  # noqa: S101 (use of assert)
        return self._loaded_command.run(self._parsed_command_args)
