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

import argparse
from unittest.mock import patch

import pytest

from craft_cli import EmitterMode, emit
from craft_cli.dispatcher import (
    _DEFAULT_GLOBAL_ARGS,
    BaseCommand,
    CommandGroup,
    Dispatcher,
    GlobalArgument,
)
from craft_cli.errors import ArgumentParsingError
from tests.factory import create_command


@pytest.fixture(autouse=True)
def init_emitter(_init_emitter):
    """Enable the init emitter fixture automatically for all this module."""


# --- Tests for the Dispatcher


def test_dispatcher_help_init():
    """Init the help infrastructure properly."""
    groups = [CommandGroup("title", [create_command("somecommand")])]
    dispatcher = Dispatcher("test-appname", groups, summary="test summary")
    assert dispatcher._help_builder.appname == "test-appname"
    assert dispatcher._help_builder.general_summary == "test summary"


def test_dispatcher_pre_parsing():
    """Parses and return global arguments."""
    groups = [CommandGroup("title", [create_command("somecommand")])]
    dispatcher = Dispatcher("appname", groups)
    global_args = dispatcher.pre_parse_args(["-q", "somecommand"])
    assert global_args == {"help": False, "verbose": False, "quiet": True, "trace": False}


def test_dispatcher_command_loading():
    """Parses and return global arguments."""
    cmd = create_command("somecommand")
    groups = [CommandGroup("title", [cmd])]
    dispatcher = Dispatcher("appname", groups)
    dispatcher.pre_parse_args(["somecommand"])
    command = dispatcher.load_command("test-config")
    assert isinstance(command, cmd)
    assert command.config == "test-config"


def test_dispatcher_missing_parsing():
    """Avoids loading the command if args not pre-parsed."""
    cmd = create_command("somecommand")
    groups = [CommandGroup("title", [cmd])]
    dispatcher = Dispatcher("appname", groups)
    with pytest.raises(RuntimeError) as exc_cm:
        dispatcher.load_command("test-config")
    assert (
        str(exc_cm.value)
        == "Need to parse arguments (call 'pre_parse_args') before loading the command."
    )


def test_dispatcher_missing_loading():
    """Avoids loading the command if args not pre-parsed."""
    cmd = create_command("somecommand")
    groups = [CommandGroup("title", [cmd])]
    dispatcher = Dispatcher("appname", groups)
    dispatcher.pre_parse_args(["-q", "somecommand"])
    with pytest.raises(RuntimeError) as exc_cm:
        dispatcher.run()
    assert str(exc_cm.value) == "Need to load the command (call 'load_command') before running it."


def test_dispatcher_command_execution_ok():
    """Command execution depends of the indicated name in command line, return code ok."""

    class MyCommandControl(BaseCommand):
        """Specifically defined command."""

        help_msg = "some help"
        overview = "fake overview"

        def run(self, parsed_args):
            self._executed.append(parsed_args)  # pylint: disable=no-member

    class MyCommand1(MyCommandControl):
        """Specifically defined command."""

        name = "name1"
        _executed = []

    class MyCommand2(MyCommandControl):
        """Specifically defined command."""

        name = "name2"
        _executed = []

    groups = [CommandGroup("title", [MyCommand1, MyCommand2])]
    dispatcher = Dispatcher("appname", groups)
    dispatcher.pre_parse_args(["name2"])
    dispatcher.load_command("config")
    dispatcher.run()
    assert MyCommand1._executed == []
    assert isinstance(MyCommand2._executed[0], argparse.Namespace)


def test_dispatcher_command_return_code():
    """Command ends indicating the return code to be used."""

    class MyCommand(BaseCommand):
        """Specifically defined command."""

        help_msg = "some help"
        name = "cmdname"
        overview = "fake overview"

        def run(self, parsed_args):
            return 17

    groups = [CommandGroup("title", [MyCommand])]
    dispatcher = Dispatcher("appname", groups)
    dispatcher.pre_parse_args(["cmdname"])
    dispatcher.load_command("config")
    retcode = dispatcher.run()
    assert retcode == 17


def test_dispatcher_command_execution_crash():
    """Command crashing doesn't pass through, we inform nicely."""

    class MyCommand(BaseCommand):
        """Specifically defined command."""

        help_msg = "some help"
        name = "cmdname"
        overview = "fake overview"

        def run(self, parsed_args):
            raise ValueError()

    groups = [CommandGroup("title", [MyCommand])]
    dispatcher = Dispatcher("appname", groups)
    dispatcher.pre_parse_args(["cmdname"])
    dispatcher.load_command("config")
    with pytest.raises(ValueError):
        dispatcher.run()


def test_dispatcher_generic_setup_default():
    """Generic parameter handling for default values."""
    cmd = create_command("somecommand")
    groups = [CommandGroup("title", [cmd])]
    emit.set_mode(EmitterMode.NORMAL)  # this is how `main` will init the Emitter
    dispatcher = Dispatcher("appname", groups)
    dispatcher.pre_parse_args(["somecommand"])
    assert emit.get_mode() == EmitterMode.NORMAL


@pytest.mark.parametrize(
    "options",
    [
        ["somecommand", "--verbose"],
        ["somecommand", "-v"],
        ["-v", "somecommand"],
        ["--verbose", "somecommand"],
        ["--verbose", "somecommand", "-v"],
    ],
)
def test_dispatcher_generic_setup_verbose(options):
    """Generic parameter handling for verbose log setup, directly or after the command."""
    cmd = create_command("somecommand")
    groups = [CommandGroup("title", [cmd])]
    emit.set_mode(EmitterMode.NORMAL)  # this is how `main` will init the Emitter
    dispatcher = Dispatcher("appname", groups)
    dispatcher.pre_parse_args(options)
    assert emit.get_mode() == EmitterMode.VERBOSE


@pytest.mark.parametrize(
    "options",
    [
        ["somecommand", "--quiet"],
        ["somecommand", "-q"],
        ["-q", "somecommand"],
        ["--quiet", "somecommand"],
        ["--quiet", "somecommand", "-q"],
    ],
)
def test_dispatcher_generic_setup_quiet(options):
    """Generic parameter handling for quiet log setup, directly or after the command."""
    cmd = create_command("somecommand")
    groups = [CommandGroup("title", [cmd])]
    emit.set_mode(EmitterMode.NORMAL)  # this is how `main` will init the Emitter
    dispatcher = Dispatcher("appname", groups)
    dispatcher.pre_parse_args(options)
    assert emit.get_mode() == EmitterMode.QUIET


@pytest.mark.parametrize(
    "options",
    [
        ["somecommand", "--trace"],
        ["somecommand", "-t"],
        ["-t", "somecommand"],
        ["--trace", "somecommand"],
        ["--trace", "somecommand", "-t"],
    ],
)
def test_dispatcher_generic_setup_trace(options):
    """Generic parameter handling for trace log setup, directly or after the command."""
    cmd = create_command("somecommand")
    groups = [CommandGroup("title", [cmd])]
    emit.set_mode(EmitterMode.NORMAL)  # this is how `main` will init the Emitter
    dispatcher = Dispatcher("appname", groups)
    dispatcher.pre_parse_args(options)
    assert emit.get_mode() == EmitterMode.TRACE


@pytest.mark.parametrize(
    "options",
    [
        ["--quiet", "--verbose", "somecommand"],
        ["-v", "-q", "somecommand"],
        ["somecommand", "--quiet", "--verbose"],
        ["somecommand", "-v", "-q"],
        ["--verbose", "somecommand", "--quiet"],
        ["-q", "somecommand", "-v"],
        ["--trace", "--verbose", "somecommand"],
        ["-v", "-t", "somecommand"],
        ["somecommand", "--trace", "--verbose"],
        ["somecommand", "-v", "-t"],
        ["--verbose", "somecommand", "--trace"],
        ["-t", "somecommand", "-v"],
        ["--quiet", "--trace", "somecommand"],
        ["-t", "-q", "somecommand"],
        ["somecommand", "--quiet", "--trace"],
        ["somecommand", "-t", "-q"],
        ["--trace", "somecommand", "--quiet"],
        ["-q", "somecommand", "-t"],
    ],
)
def test_dispatcher_generic_setup_mutually_exclusive(options):
    """Disallow mutually exclusive generic options."""
    cmd = create_command("somecommand")
    groups = [CommandGroup("title", [cmd])]
    dispatcher = Dispatcher("appname", groups)
    with pytest.raises(ArgumentParsingError) as err:
        dispatcher.pre_parse_args(options)
    assert str(err.value) == "The 'verbose', 'trace' and 'quiet' options are mutually exclusive."


@pytest.mark.parametrize(
    "options",
    [
        ["somecommand", "--globalparam", "foobar"],
        ["somecommand", "--globalparam=foobar"],
        ["somecommand", "-g", "foobar"],
        ["-g", "foobar", "somecommand"],
        ["--globalparam", "foobar", "somecommand"],
        ["--globalparam=foobar", "somecommand"],
    ],
)
def test_dispatcher_generic_setup_paramglobal_with_param(options):
    """Generic parameter handling for a param type global arg, directly or after the cmd."""
    cmd = create_command("somecommand")
    groups = [CommandGroup("title", [cmd])]
    extra = GlobalArgument("globalparam", "option", "-g", "--globalparam", "Test global param.")
    dispatcher = Dispatcher("appname", groups, extra_global_args=[extra])
    global_args = dispatcher.pre_parse_args(options)
    assert global_args["globalparam"] == "foobar"


@pytest.mark.parametrize(
    "options",
    [
        ["somecommand", "--globalparam"],
        ["somecommand", "--globalparam="],
        ["somecommand", "-g"],
        ["--globalparam=", "somecommand"],
    ],
)
def test_dispatcher_generic_setup_paramglobal_without_param_simple(options):
    """Generic parameter handling for a param type global arg without the requested parameter."""
    cmd = create_command("somecommand")
    groups = [CommandGroup("title", [cmd])]
    extra = GlobalArgument("globalparam", "option", "-g", "--globalparam", "Test global param.")
    dispatcher = Dispatcher("appname", groups, extra_global_args=[extra])
    with pytest.raises(ArgumentParsingError) as err:
        dispatcher.pre_parse_args(options)
    assert str(err.value) == "The 'globalparam' option expects one argument."


@pytest.mark.parametrize(
    "options",
    [
        ["-g", "somecommand"],
        ["--globalparam", "somecommand"],
    ],
)
def test_dispatcher_generic_setup_paramglobal_without_param_confusing(options):
    """Generic parameter handling for a param type global arg confusing the command as the arg."""
    cmd = create_command("somecommand")
    groups = [CommandGroup("title", [cmd])]
    extra = GlobalArgument("globalparam", "option", "-g", "--globalparam", "Test global param.")
    dispatcher = Dispatcher("appname", groups, extra_global_args=[extra])
    with patch("craft_cli.helptexts.HelpBuilder.get_full_help") as mock_helper:
        mock_helper.return_value = "help text"
        with pytest.raises(ArgumentParsingError) as err:
            dispatcher.pre_parse_args(options)

    # generic usage message because "no command" (as 'somecommand' was consumed by --globalparam)
    assert str(err.value) == "help text"


def test_dispatcher_build_commands_ok():
    """Correct command loading."""
    cmd0, cmd1, cmd2 = [create_command(f"cmd-name-{n}", "cmd help") for n in range(3)]
    groups = [
        CommandGroup("whatever title", [cmd0]),
        CommandGroup("other title", [cmd1, cmd2]),
    ]
    dispatcher = Dispatcher("appname", groups)
    assert len(dispatcher.commands) == 3
    for cmd in [cmd0, cmd1, cmd2]:
        expected_class = dispatcher.commands[cmd.name]
        assert expected_class == cmd


def test_dispatcher_build_commands_repeated():
    """Error while loading commands with repeated name."""

    class Foo(BaseCommand):
        """Specifically defined command."""

        help_msg = "some help"
        name = "repeated"

    class Bar(BaseCommand):
        """Specifically defined command."""

        help_msg = "some help"
        name = "cool"

    class Baz(BaseCommand):
        """Specifically defined command."""

        help_msg = "some help"
        name = "repeated"

    groups = [
        CommandGroup("whatever title", [Foo, Bar]),
        CommandGroup("other title", [Baz]),
    ]
    expected_msg = "Multiple commands with same name: (Foo|Baz) and (Baz|Foo)"
    with pytest.raises(RuntimeError, match=expected_msg):
        Dispatcher("appname", groups)


def test_dispatcher_commands_are_not_loaded_if_not_needed():
    class MyCommand1(BaseCommand):
        """Expected to be executed."""

        name = "command1"
        help_msg = "some help"
        overview = "fake overview"
        _executed = []

        def run(self, parsed_args):
            self._executed.append(parsed_args)

    class MyCommand2(BaseCommand):
        """Expected to not be instantiated, or parse args, or run."""

        name = "command2"
        help_msg = "some help"
        overview = "fake overview"

        def __init__(self, *args):  # pylint: disable=super-init-not-called
            raise AssertionError

        def fill_parser(self, parser):
            raise AssertionError

        def run(self, parsed_args):
            raise AssertionError

    groups = [CommandGroup("title", [MyCommand1, MyCommand2])]
    dispatcher = Dispatcher("appname", groups)
    dispatcher.pre_parse_args(["command1"])
    dispatcher.load_command("config")
    dispatcher.run()
    assert isinstance(MyCommand1._executed[0], argparse.Namespace)


def test_dispatcher_global_arguments_default():
    """The dispatcher uses the default global arguments."""
    cmd = create_command("somecommand")
    groups = [CommandGroup("title", [cmd])]

    dispatcher = Dispatcher("appname", groups)
    assert dispatcher.global_arguments == _DEFAULT_GLOBAL_ARGS


def test_dispatcher_global_arguments_extra_arguments():
    """The dispatcher uses the default global arguments."""
    cmd = create_command("somecommand")
    groups = [CommandGroup("title", [cmd])]

    extra_arg = GlobalArgument("other", "flag", "-o", "--other", "Other stuff")
    dispatcher = Dispatcher("appname", groups, extra_global_args=[extra_arg])
    assert dispatcher.global_arguments == _DEFAULT_GLOBAL_ARGS + [extra_arg]


# --- Tests for the base command


def test_basecommand_holds_the_indicated_info():
    """BaseCommand subclasses ."""

    class TestCommand(BaseCommand):
        """Specifically defined command."""

        help_msg = "help message"
        name = "test"
        overview = "fake overview"

    config = "test config"
    command = TestCommand(config)
    assert command.config == config


def test_basecommand_fill_parser_optional():
    """BaseCommand subclasses are allowed to not override fill_parser."""

    class TestCommand(BaseCommand):
        """Specifically defined command."""

        help_msg = "help message"
        name = "test"
        overview = "fake overview"

        def __init__(self, config):
            self.done = False
            super().__init__(config)

        def run(self, parsed_args):
            self.done = True

    command = TestCommand("config")
    command.run([])
    assert command.done


def test_basecommand_run_mandatory():
    """BaseCommand subclasses must override run."""

    class TestCommand(BaseCommand):
        """Specifically defined command."""

        help_msg = "help message"
        name = "test"
        overview = "fake overview"

    command = TestCommand("config")
    with pytest.raises(NotImplementedError):
        command.run([])


def test_basecommand_mandatory_attribute_name():
    """BaseCommand subclasses must override the name attribute."""

    class TestCommand(BaseCommand):
        """Specifically defined command."""

        help_msg = "help message"
        overview = "fake overview"

    with pytest.raises(TypeError):
        TestCommand("config")  # pylint: disable=abstract-class-instantiated


def test_basecommand_mandatory_attribute_help_message():
    """BaseCommand subclasses must override the help_message attribute."""

    class TestCommand(BaseCommand):
        """Specifically defined command."""

        overview = "fake overview"
        name = "test"

    with pytest.raises(TypeError):
        TestCommand("config")  # pylint: disable=abstract-class-instantiated


def test_basecommand_mandatory_attribute_overview():
    """BaseCommand subclasses must override the overview attribute."""

    class TestCommand(BaseCommand):
        """Specifically defined command."""

        help_msg = "help message"
        name = "test"

    with pytest.raises(TypeError):
        TestCommand("config")  # pylint: disable=abstract-class-instantiated
