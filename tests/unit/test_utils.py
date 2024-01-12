# Copyright 2024 Canonical Ltd.
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
"""Unit tests for utility functions."""
import re

import pytest
import pytest_check
from hypothesis import given, strategies

from craft_cli import utils


@pytest.mark.parametrize(
    "values",
    [
        [],
        ["one-thing"],
        ["two", "things"],
    ],
)
@pytest.mark.parametrize("conjunction", ["and", "or", "but not"])
def test_humanise_list_success(values, conjunction):
    actual = utils.humanise_list(values, conjunction)

    pytest_check.equal(actual.count(","), max((len(values) - 2, 0)))
    with pytest_check.check:
        assert actual == "" or conjunction in actual
    for value in values:
        pytest_check.is_in(value, actual)


@given(
    values=strategies.lists(strategies.text()),
    conjunction=strategies.text(),
)
def test_humanise_list_fuzzy(values, conjunction):
    actual = utils.humanise_list(values, conjunction)

    pytest_check.greater_equal(actual.count(","), max((len(values) - 2, 0)))
    with pytest_check.check:
        assert actual == "" or conjunction in actual
    for value in values:
        pytest_check.is_in(value, actual)
