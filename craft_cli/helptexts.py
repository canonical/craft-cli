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

"""Provide all help texts."""

from __future__ import annotations

import argparse
import enum
import textwrap
from operator import attrgetter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from craft_cli.dispatcher import BaseCommand, CommandGroup


# if the `help` of any argument (global or for any command, option or parameter) is set to this
# value, the argument will not be shown in help messages; the default is to support the
# non-documented argparse attribute (so if users were using it, will just work) in a secure way
# in case it disappears in the future.
HIDDEN = argparse.SUPPRESS

# max columns used in the terminal
TERMINAL_WIDTH = 72

# generic intro and outro texts
HEADER = """
Usage:
    {appname} [help] <command>
"""

USAGE = """\
Usage: {appname} [options] command [args]...
Try '{full_command} -h' for help.

Error: {error_message}
"""


# the used formats, defaults to first one
OutputFormat = enum.Enum("OutputFormat", "plain markdown")


def _build_item_plain(title: str, text: str, title_space: int) -> list[str]:
    """Prepare an item for the help in plain format, generically a title and a text aligned.

    This is how the plain mode is built:
    - the title starts in column 4 with an extra ':', aligned to the right
    - the text starts in 4 plus the title space; if too wide it's wrapped.
    """
    # wrap the general text to the desired max width (discounting the space for the title,
    # the first 4 spaces, the two spaces to separate title/text, and the ':'
    not_title_space = 7
    text_space = TERMINAL_WIDTH - title_space - not_title_space
    wrapped_lines = textwrap.wrap(text, text_space)

    # first line goes with the title at column 4
    first = f"    {title:>{title_space}s}:  {wrapped_lines[0]}"
    result = [first]

    # the rest (if any) still aligned but without title
    for line in wrapped_lines[1:]:
        result.append(" " * (title_space + not_title_space) + line)

    return result


def process_overview_for_markdown(text: str) -> str:
    """Process a regular overview to be rendered with markdown.

    In detail:

    - Join all lines for the same paragraph (as wrapping is responsibility of the renderer)

    - Dedent and wrap with triple-backtick all indented blocks

    Paragraphs are separated by empty lines
    """
    lines = [x.rstrip() for x in text.strip().split("\n")]

    # group all the lines in different blocks, each holding what would be a
    # paragraph (detected by the empty line that separates them)
    blocks: list[list[str]] = [[]]
    for line in lines:
        if line:
            blocks[-1].append(line)
        else:
            blocks.append([])

    # convert each of the block/paragraph into their markdown representation
    result: list[str] = []
    for block in blocks:
        if block and block[0] and block[0][0] == " ":
            # it is indented! dedent and wrap with backticks
            dedented = textwrap.dedent("\n".join(block))
            text = f"```text\n{dedented}\n```"
        else:
            # regular text
            text = " ".join(block)

        # include the processed text and an empty line; this empty line will be a separation
        # between paragraphs or the final newline at the end of the whole text
        result.extend((text, ""))

    return "\n".join(result)


class HelpBuilder:
    """Produce the different help texts."""

    def __init__(
        self, appname: str, general_summary: str, command_groups: list[CommandGroup]
    ) -> None:
        self.appname = appname
        self.general_summary = general_summary
        self.command_groups = command_groups

    def get_usage_message(self, error_message: str, command: str = "") -> str:
        """Build a usage and error message.

        The command is the extra string used after the application name to build the
        full command that will be shown in the usage message; for example, having an
        application name of "someapp":
        - if command is "" it will be shown "Try 'appname -h' for help".
        - if command is "version" it will be shown "Try 'appname version -h' for help"

        The error message is the specific problem in the given parameters.
        """
        full_command = f"{self.appname} {command}" if command else self.appname
        return USAGE.format(
            appname=self.appname, full_command=full_command, error_message=error_message
        )

    def get_full_help(self, global_options: list[tuple[str, str]]) -> str:
        """Produce the text for the default help.

        - global_options: options defined at application level (not in the commands),
          with the (options, description) structure

        The help text has the following structure:

        - usage
        - summary
        - common commands listed and described shortly
        - all commands grouped, just listed
        - more help
        """
        textblocks = []

        # title
        textblocks.append(HEADER.format(appname=self.appname))

        # summary
        textblocks.append("Summary:" + textwrap.indent(self.general_summary, "    "))

        # column alignment is dictated by longest common commands names and groups names
        max_title_len = 0

        # collect common commands
        common_commands = []
        for command_group in self.command_groups:
            max_title_len = max(len(command_group.name), max_title_len)
            for cmd in command_group.commands:
                if cmd.common:
                    common_commands.append(cmd)
                    max_title_len = max(len(cmd.name), max_title_len)

        for title, _ in global_options:
            max_title_len = max(len(title), max_title_len)

        global_lines = ["Global options:"]
        for title, text in global_options:
            if text is not HIDDEN:
                global_lines.extend(_build_item_plain(title, text, max_title_len))
        textblocks.append("\n".join(global_lines))

        common_lines = ["Starter commands:"]
        for cmd in sorted(common_commands, key=attrgetter("name")):
            common_lines.extend(_build_item_plain(cmd.name, cmd.help_msg, max_title_len))
        textblocks.append("\n".join(common_lines))

        grouped_lines = ["Commands can be classified as follows:"]
        for command_group in sorted(self.command_groups, key=attrgetter("name")):
            command_names = [cmd.name for cmd in command_group.commands if not cmd.hidden]
            if not command_group.ordered:
                command_names.sort()
            command_names_str = ", ".join(command_names)
            grouped_lines.extend(
                _build_item_plain(command_group.name, command_names_str, max_title_len)
            )
        textblocks.append("\n".join(grouped_lines))

        textblocks.append(
            textwrap.dedent(
                f"""
            For more information about a command, run '{self.appname} help <command>'.
            For a summary of all commands, run '{self.appname} help --all'.
        """
            )
        )

        # join all stripped blocks, leaving ONE empty blank line between
        return "\n\n".join(block.strip() for block in textblocks) + "\n"

    def get_detailed_help(self, global_options: list[tuple[str, str]]) -> str:
        """Produce the text for the detailed help.

        - global_options: options defined at application level (not in the commands),
          with the (options, description) structure

        The help text has the following structure:

        - usage
        - summary
        - global options
        - all commands shown with description, grouped
        - more help
        """
        textblocks = []

        # title
        textblocks.append(HEADER.format(appname=self.appname))

        # summary
        textblocks.append("Summary:" + textwrap.indent(self.general_summary, "    "))

        # column alignment is dictated by longest common commands names and groups names
        max_title_len = 0
        for command_group in self.command_groups:
            for cmd in command_group.commands:
                max_title_len = max(len(cmd.name), max_title_len)
        for title, _ in global_options:
            max_title_len = max(len(title), max_title_len)

        global_lines = ["Global options:"]
        for title, text in global_options:
            if text is not HIDDEN:
                global_lines.extend(_build_item_plain(title, text, max_title_len))
        textblocks.append("\n".join(global_lines))

        textblocks.append("Commands can be classified as follows:")

        for command_group in self.command_groups:
            group_lines = [f"{command_group.name}:"]
            for cmd in command_group.commands:
                if cmd.hidden:
                    continue
                group_lines.extend(_build_item_plain(cmd.name, cmd.help_msg, max_title_len))
            textblocks.append("\n".join(group_lines))

        textblocks.append(
            textwrap.dedent(
                f"""
            For more information about a specific command, run '{self.appname} help <command>'.
        """
            )
        )

        # join all stripped blocks, leaving ONE empty blank line between
        return "\n\n".join(block.strip() for block in textblocks) + "\n"

    def _build_plain_command_help(
        self,
        usage: str,
        overview: str,
        options: list[tuple[str, str]],
        other_command_names: list[str],
    ) -> list[str]:
        """Build the command help in its plain version.

        The help text has the following structure:

        - usage
        - summary
        - options
        - other related commands
        - footer
        """
        textblocks = []

        textblocks.append(
            textwrap.dedent(
                f"""\
                Usage:
                    {usage}
            """
            )
        )

        overview = textwrap.indent(overview, "    ")
        textblocks.append(f"Summary:{overview}")

        # column alignment is dictated by longest options title
        max_title_len = max(len(title) for title, text in options)

        # command options
        option_lines = ["Options:"]
        for title, text in options:
            option_lines.extend(_build_item_plain(title, text, max_title_len))
        textblocks.append("\n".join(option_lines))

        if other_command_names:
            see_also_block = ["See also:"]
            see_also_block.extend(("    " + name) for name in sorted(other_command_names))
            textblocks.append("\n".join(see_also_block))

        # footer
        textblocks.append(
            f"""
            For a summary of all commands, run '{self.appname} help --all'.
        """
        )

        return textblocks

    def _build_markdown_command_help(
        self,
        usage: str,
        overview: str,
        options: list[tuple[str, str]],
        other_command_names: list[str],
    ) -> list[str]:
        """Build the command help in its markdown version.

        The help text has the following structure:

        - usage
        - summary
        - options
        - other related commands
        - footer
        """
        textblocks = []

        textblocks.append(
            textwrap.dedent(
                f"""\
            ## Usage:
            ```text
            {usage}
            ```
        """
            )
        )

        overview = process_overview_for_markdown(overview)
        textblocks.append(f"## Summary:\n\n{overview}")

        option_lines = [
            "## Options:",
            "| | |",
            "|-|-|",
        ]
        for title, text in options:
            option_lines.append(f"| `{title}` | {text} |")

        textblocks.append("\n".join(option_lines))

        if other_command_names:
            see_also_block = ["## See also:"]
            see_also_block.extend(f"- `{name}`" for name in sorted(other_command_names))
            textblocks.append("\n".join(see_also_block))

        return textblocks

    def get_command_help(
        self,
        command: BaseCommand,
        arguments: list[tuple[str, str]],
        output_format: OutputFormat,
    ) -> str:
        """Produce the text for each command's help in any output format.

        - command: the instantiated command for which help is prepared

        - arguments: all command options and parameters, with the (name, description) structure;
            note that any argument with description being `HIDDEN` will be ignored

        - output_format: the selected output format

        The help text structure depends of the output format.
        """
        # separate all arguments into the parameters and optional ones, just checking
        # if first char is a dash
        parameters = []
        options = []
        for name, title in arguments:
            if title is HIDDEN:
                continue
            if name[0] == "-":
                options.append((name, title))
            else:
                parameters.append(name)

        usage = f"{self.appname} {command.name} [options]"
        if parameters:
            usage += " " + " ".join(f"<{parameter}>" for parameter in parameters)

        for command_group in self.command_groups:
            if any(isinstance(command, command_class) for command_class in command_group.commands):
                break
        else:
            raise RuntimeError("Internal inconsistency in commands groups")
        other_command_names = [
            c.name for c in command_group.commands if not isinstance(command, c)
        ]

        if output_format == OutputFormat.markdown:
            builder = self._build_markdown_command_help
        else:
            builder = self._build_plain_command_help
        textblocks = builder(usage, command.overview, options, other_command_names)

        # join all stripped blocks, leaving ONE empty blank line between
        return "\n\n".join(block.strip() for block in textblocks) + "\n"
