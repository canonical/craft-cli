#
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

"""Error classes."""

from typing import Optional


class CraftError(Exception):
    """Signal a program error with a lot of information to report.

    :ivar message: the main message to the user, to be shown as first line (and
      probably only that, according to the different modes); note that in some
      cases the log location will be attached to this message.

    :ivar details: the full error details received from a third party which
      originated the error situation

    :ivar resolution: an extra line indicating to the user how the error may be
      fixed or avoided (to be shown together with 'message')

    :ivar docs_url: an URL to point the user to documentation (to be shown
      together with 'message')

    :ivar reportable: if an error report should be sent to some error-handling
      backend (like Sentry)

    :ivar retcode: the code to return when the application finishes
    """

    def __init__(
        self,
        message: str,
        *,
        details: Optional[str] = None,
        resolution: Optional[str] = None,
        docs_url: Optional[str] = None,
        reportable: bool = True,
        retcode: int = 1,
    ):
        super().__init__(message)
        self.details = details
        self.resolution = resolution
        self.docs_url = docs_url
        self.reportable = reportable
        self.retcode = retcode

    def __eq__(self, other):
        if isinstance(other, CraftError):
            return all(
                [
                    self.args == getattr(other, "args"),
                    self.details == getattr(other, "details"),
                    self.resolution == getattr(other, "resolution"),
                    self.docs_url == getattr(other, "docs_url"),
                    self.reportable == getattr(other, "reportable"),
                    self.retcode == getattr(other, "retcode"),
                ]
            )
        else:
            return NotImplemented
