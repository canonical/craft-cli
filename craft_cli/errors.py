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

__all__ = [
    "CraftError",
]

from typing import Any, cast


class CraftError(Exception):
    """Signal a program error with a lot of information to report."""

    message: str
    """The main message to the user, to be shown as first line (and probably only that,
      according to the different modes); note that in some cases the log location will be
      attached to this message."""

    details: str | None
    """The full error details received from a third party which originated the error
      situation."""

    resolution: str | None
    """An extra line indicating to the user how the error may be fixed or avoided (to be
      shown together with ``message``)."""

    docs_url: str | None
    """An URL to point the user to documentation (to be shown together with ``message``)."""

    doc_slug: str | None
    """The slug to the user documentation. Needs a base url to form a full address.
      Note that ``docs_url`` has preference if it is set."""

    logpath_report: bool
    """Whether the location of the log filepath should be presented in the screen as the
     final message."""

    reportable: bool
    """If an error report should be sent to some error-handling backend (like Sentry)."""

    retcode: int
    """The code to return when the application finishes."""

    def __init__(  # noqa: PLR0913 (too many arguments)
        self,
        message: str,
        *,
        details: str | None = None,
        resolution: str | None = None,
        docs_url: str | None = None,
        logpath_report: bool = True,
        reportable: bool = True,
        retcode: int = 1,
        doc_slug: str | None = None,
    ) -> None:
        super().__init__(message)
        self.details = details
        self.resolution = resolution
        self.docs_url = docs_url
        self.logpath_report = logpath_report
        self.reportable = reportable
        self.retcode = retcode
        self.doc_slug = doc_slug
        if doc_slug and not doc_slug.startswith("/"):
            self.doc_slug = "/" + doc_slug

    def __eq__(self, other: object) -> bool:
        if isinstance(other, CraftError):
            return all(
                [
                    self.args == other.args,
                    self.details == other.details,
                    self.resolution == other.resolution,
                    self.docs_url == other.docs_url,
                    self.logpath_report == other.logpath_report,
                    self.reportable == other.reportable,
                    self.retcode == other.retcode,
                    self.doc_slug == other.doc_slug,
                ]
            )
        return NotImplemented


class CraftCommandError(CraftError):
    """A CraftError with precise error output from a command.

    This exception class augments CraftError with the addition of a ``stderr``
    parameter. This parameter is meant to hold the standard error contents of
    the failed command - as such, it sits between the typically brief "message"
    and the "details" parameters from the point of view of verbosity.

    It's meant to be used in cases where the executed command's standard error
    is helpful enough to the user to be worth the extra text output.
    """

    def __init__(self, message: str, *, stderr: str | bytes | None, **kwargs: Any) -> None:
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
