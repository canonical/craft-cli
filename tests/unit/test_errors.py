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

"""Tests for errors."""

import pytest

from craft_cli.errors import CraftError


def test_crafterror_is_comparable():
    error1 = CraftError("foo")
    error2 = CraftError("foo")

    assert error1 == error2


def test_crafterror_is_different():
    error1 = CraftError("foo")
    error2 = CraftError("bar")

    assert error1 != error2


def test_crafterror_does_not_compare_to_other_exception():
    error1 = CraftError("foo")
    error2 = ValueError("foo")

    assert error1 != error2


@pytest.mark.parametrize(
    "argument_name",
    [
        "details",
        "resolution",
        "docs_url",
        "reportable",
        "retcode",
    ],
)
def test_compare_crafterror_with_different_attribute_values(argument_name):
    error1 = CraftError("message")
    error2 = CraftError("message")
    setattr(error1, argument_name, "foo")
    setattr(error2, argument_name, "bar")

    assert error1 != error2


@pytest.mark.parametrize(
    "argument_name",
    [
        "details",
        "resolution",
        "docs_url",
        "reportable",
        "retcode",
    ],
)
def test_compare_crafterror_with_identical_attribute_values(argument_name):
    error1 = CraftError("message")
    error2 = CraftError("message")
    setattr(error1, argument_name, "foo")
    setattr(error2, argument_name, "foo")

    assert error1 == error2
