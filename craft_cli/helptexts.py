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

import textwrap
from operator import attrgetter
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from craft_cli.dispatcher import BaseCommand, CommandGroup


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


def _build_item(title: str, text: str, title_space: int) -> List[str]:
    """Show an item in the help, generically a title and a text aligned.

    The title starts in column 4 with an extra ':'. The text starts in
    4 plus the title space; if too wide it's wrapped.
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


class HelpBuilder:
    """Produce the different help texts."""

    def __init__(self, appname: str, general_summary: str, command_groups: List["CommandGroup"]):
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
        if command:
            full_command = f"{self.appname} {command}"
        else:
            full_command = self.appname
        return USAGE.format(
            appname=self.appname, full_command=full_command, error_message=error_message
        )

    def get_full_help(self, global_options: List[Tuple[str, str]]) -> str:
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
            global_lines.extend(_build_item(title, text, max_title_len))
        textblocks.append("\n".join(global_lines))

        common_lines = ["Starter commands:"]
        for cmd in sorted(common_commands, key=attrgetter("name")):
            common_lines.extend(_build_item(cmd.name, cmd.help_msg, max_title_len))
        textblocks.append("\n".join(common_lines))

        grouped_lines = ["Commands can be classified as follows:"]
        for command_group in sorted(self.command_groups, key=attrgetter("name")):
            command_names = ", ".join(sorted(cmd.name for cmd in command_group.commands))
            grouped_lines.extend(_build_item(command_group.name, command_names, max_title_len))
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
        text = "\n\n".join(block.strip() for block in textblocks) + "\n"
        return text

    def get_detailed_help(self, global_options: List[Tuple[str, str]]) -> str:
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
            global_lines.extend(_build_item(title, text, max_title_len))
        textblocks.append("\n".join(global_lines))

        textblocks.append("Commands can be classified as follows:")

        for command_group in self.command_groups:
            group_lines = [f"{command_group.name}:"]
            for cmd in command_group.commands:
                group_lines.extend(_build_item(cmd.name, cmd.help_msg, max_title_len))
            textblocks.append("\n".join(group_lines))

        textblocks.append(
            textwrap.dedent(
                f"""
            For more information about a specific command, run '{self.appname} help <command>'.
        """
            )
        )

        # join all stripped blocks, leaving ONE empty blank line between
        text = "\n\n".join(block.strip() for block in textblocks) + "\n"
        return text

    def get_command_help(  # pylint: disable=too-many-locals
        self, command: "BaseCommand", arguments: List[Tuple[str, str]]
    ) -> str:
        """Produce the text for each command's help.

        - command: the instantiated command for which help is prepared

        - arguments: all command options and parameters, with the (name, description) structure

        The help text has the following structure:

        - usage
        - summary
        - options
        - other related commands
        - footer
        """
        textblocks = []

        # separate all arguments into the parameters and optional ones, just checking
        # if first char is a dash
        parameters = []
        options = []
        for name, title in arguments:
            if name[0] == "-":
                options.append((name, title))
            else:
                parameters.append(name)

        joined_params = " ".join(f"<{parameter}>" for parameter in parameters)
        textblocks.append(
            textwrap.dedent(
                f"""\
            Usage:
                {self.appname} {command.name} [options] {joined_params}
        """
            )
        )

        assert command.overview is not None  # for typing purposes
        indented_overview = textwrap.indent(command.overview, "    ")
        textblocks.append(f"Summary:{indented_overview}")

        # column alignment is dictated by longest options title
        max_title_len = max(len(title) for title, text in options)

        # command options
        option_lines = ["Options:"]
        for title, text in options:
            option_lines.extend(_build_item(title, text, max_title_len))
        textblocks.append("\n".join(option_lines))

        # recommend other commands of the same group
        for command_group in self.command_groups:
            if any(isinstance(command, command_class) for command_class in command_group.commands):
                break
        else:
            raise RuntimeError("Internal inconsistency in commands groups")
        other_command_names = [
            c.name
            for c in command_group.commands  # pylint: disable=undefined-loop-variable
            if not isinstance(command, c)
        ]
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

        # join all stripped blocks, leaving ONE empty blank line between
        text = "\n\n".join(block.strip() for block in textblocks) + "\n"
        return text
