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

from typing import Type

from craft_cli import BaseCommand


def create_command(
    name: str,
    help_msg: str = "",
    *,
    common: bool = False,
    hidden: bool = False,
    overview: str = "",
    class_name: str = "MyCommand",
) -> Type["BaseCommand"]:
    """Helper to create commands."""
    attribs = {
        "name": name,
        "help_msg": help_msg,
        "common": common,
        "hidden": hidden,
        "overview": overview,
        "needs_config": False,
        "run": lambda parsed_args: None,
    }
    return type(class_name, (BaseCommand,), attribs)
