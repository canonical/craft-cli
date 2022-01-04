# Copyright 2021 Canonical Ltd.
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

from typing import Type, TYPE_CHECKING

from craft_cli import BaseCommand

if TYPE_CHECKING:
    from craft_cli.dispatcher import _CommandType


class TypingHelper(BaseCommand):
    """Intermediate subclasser just to make typing system happy in create_command's return."""


def create_command(
    name_: str,
    help_msg_: str = "",
    common_: bool = False,
    overview_: str = "",
    needs_config_: bool = False,
) -> Type["_CommandType"]:
    """Helper to create commands."""
    if help_msg_ is None:
        help_msg_ = "Automatic help generated in the factory for the tests."
    if overview_ is None:
        overview_ = "Automatic long description generated in the factory for the tests."

    class MyCommand(BaseCommand):
        """Specifically defined command."""

        name = name_
        help_msg = help_msg_
        common = common_
        overview = overview_
        needs_config = needs_config_

        def run(self, parsed_args):
            pass

    return MyCommand
