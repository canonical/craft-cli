#
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

"""Interact with Canonical services such as Charmhub and the Snap Store."""

__version__ = "0.3.0"

# names included here only to be exposed as external API; the particular order of imports
# is to break cyclic dependencies
from .messages import EmitterMode, emit  # noqa: F401 ; isort:skip
from .dispatcher import BaseCommand, CommandGroup, Dispatcher, GlobalArgument  # noqa: F401
from .errors import ArgumentParsingError, CraftError, ProvideHelpException  # noqa: F401

__all__ = [
    "ArgumentParsingError",
    "BaseCommand",
    "CommandGroup",
    "CraftError",
    "Dispatcher",
    "EmitterMode",
    "GlobalArgument",
    "ProvideHelpException",
    "emit",
]
