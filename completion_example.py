#!/bin/env python3
"""This is an example of how to generate bash completion.

This script is complete and runs as-is, printing bash completion for the
example CLI generated.
"""
import argparse
import pathlib
from typing import Optional

import pydantic

import craft_cli
from craft_cli.dispatcher import _CustomArgumentParser


class LsCommand(craft_cli.BaseCommand):
    name = "ls"
    help_msg = "Simulate ls"
    overview = "Simulates ls"

    def fill_parser(self, parser: _CustomArgumentParser) -> None:
        parser.add_argument("-a", "--all", action="store_true", help="Output all hidden files")
        parser.add_argument("--color", choices=["always", "auto", "never"], help="When to output in color")
        parser.add_argument("path", nargs="*", type=pathlib.Path, help="Path to list")


class CpCommand(craft_cli.BaseCommand):
    name = "cp"
    help_msg = "cp"
    overview = "cp"

    def fill_parser(self, parser: _CustomArgumentParser) -> None:
        parser.add_argument("src", type=pathlib.Path)
        parser.add_argument("dest", type=pathlib.Path)


basic_group = craft_cli.CommandGroup("basic", [LsCommand, CpCommand])

extra_global_args = []

cmd = craft_cli.Dispatcher(
    appname="pybash",
    commands_groups=[basic_group],
    extra_global_args=extra_global_args,
)

from craft_cli import completion

print(completion.complete("pybash", cmd))
