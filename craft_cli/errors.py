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

    - message: the main message to the user, to be shown as first line (and probably
      only that, according to the different modes); note that in some cases the log
      location will be attached to this message.

    - details: the full error details received from a third party which originated
      the error situation

    - resolution: an extra line indicating to the user how the error may be fixed or
      avoided (to be shown together with 'message')

    - docs_url: an URL to point the user to documentation (to be shown together
      with 'message')

    - reportable: if an error report should be sent to some error-handling backend (like
      Sentry)

    - retcode: the code to return when the application finishes
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
