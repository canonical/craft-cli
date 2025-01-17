"""Bash completion script generation module."""

from .completion import (
    complete,
    get_set_flags,
    Action,
    Arg,
    Argument,
    CommandMapping,
    CompGen,
    Option,
)

__all__ = [
    "complete",
    "get_set_flags",
    "Arg",
    "Action",
    "Argument",
    "Option",
    "CommandMapping",
    "CompGen",
]
