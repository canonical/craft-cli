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

"""Error classes."""

from typing import Any, cast

from craft_cli._rs.errors import CraftError

__all__ = [
    "CraftError",
]


class CraftCommandError(CraftError):
    """A CraftError with precise error output from a command.

    This exception class augments CraftError with the addition of a ``stderr``
    parameter. This parameter is meant to hold the standard error contents of
    the failed command - as such, it sits between the typically brief "message"
    and the "details" parameters from the point of view of verbosity.

    It's meant to be used in cases where the executed command's standard error
    is helpful enough to the user to be worth the extra text output.
    """

    def __init__(
        self, message: str, *, stderr: str | bytes | None, **kwargs: Any
    ) -> None:
        super().__init__(message, **kwargs)
        self._stderr = stderr

    @property
    def stderr(self) -> str | None:
        if isinstance(self._stderr, bytes):
            return self._stderr.decode("utf8", errors="replace")
        # pyright needs the cast here
        return cast("str | None", self._stderr)  # type: ignore[redundant-cast]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, CraftCommandError):
            return self._stderr == other._stderr and super().__eq__(other)
        return NotImplemented


class ArgumentParsingError(Exception):
    """Exception used when an argument parsing error is found."""


class ProvideHelpException(Exception):  # noqa: N818 (Exception should have an Error suffix)
    """Exception used to provide help to the user."""
