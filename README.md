# Craft CLI

A Command Line Client builder that follows Canonical's guidelines for a command line
interface defined [in this forum post](https://discourse.ubuntu.com/c/design/cli-guidelines/62).

The library provides two main functionalities: 

- a framework to define and execute application commands, which involves argument parsing and the provision of help texts

- infrastructure to handle the terminal and present all the outputs for the different application needs


# Usage

The interfaces to the main library functionalities are the `emit` and `Dispatcher` objects, the former to present messages to the user, and the later to parse arguments and run the application commands. The usage of both interfaces is described later (see [emit](FIXME) or [Dispatcher](FIXME)).

The library also provides an easy way to create the different commands (see [here](FIXME)), and a structured way to raise application errors (see [here](FIXME)).

This first section is to present how the whole library can be properly setup and used.


## Library Setup

For best usage of the library's functionality the recommendation is to wrap all the application execution in a comprehensive try/except block to finish properly (close everything, and produce proper error messages if something went bad) no matter how the command itself results.

The following is a simple structure to show this:

```python
from craft_cli import emit, CraftError, EmitterMode
...
emit.init(EmitterMode.NORMAL, "my-app-name", f"Starting super app v3")
...
try:
    # all app execution
    ...
except Exception as exc:
    error = CraftError(f"Application internal error: {exc!r}") 
    error.__cause__ = exc
    emit.error(error)
else:
    emit.ended_ok()
```

Several things to note in that code:
- before using anything from the library, the `emit` object needs to be initiated, passing the verboseness mode, the application name, and a greeting message (see [this section](FIXME) for more info about this).
- all the application execution is in the `try` block; this section will include all `Dispatcher` usage, as shown later in an expanded example
- on any error, a CraftError is created with a custom message and `emit` is called to present the error situation (to the user, logs, etc), which will close it properly; note the assignment of the original exception to the new error's `__cause__`: it will used to enhance the produced information
- if no problems arised, the `emit` object is ended ok, to properly close the terminal's usage

The application execution involves instantiating and using `Dispatcher`. A simple example is presented here (see [this section](FIXME) for more info), introducing also the handling of an application's return code:


```python
import sys
from craft_cli import emit, CraftError, Dispatcher
...
emit.init(EmitterMode.NORMAL, "my-app-name", f"Starting super app v3")
...
try:
    dispatcher = Dispatcher("my-app-name", COMMAND_GROUPS, summary="What's the app about")
    dispatcher.pre_parse_args(sys.argv[1:])
    dispatcher.load_command(None)
    retcode = dispatcher.run()
except Exception as exc:
    error = CraftError(f"Application internal error: {exc!r}") 
    error.__cause__ = exc
    emit.error(error)
    retcode = 1
else:
    emit.ended_ok()
    if retcode is None:
        retcode = 0
sys.exit(retcode)
```

Note that the return code is `1` when ending in error, and when ending succesfully, it will be `0` unless the command itself returned a specific code.

The error handling should be improved. On one hand the Dispatcher may raise two specific exceptions to end the program because of error when parsing arguments or to present help to ther user, and on the other hand the application may have internal errors to handle specific situations.

A more comprehensive setup example, then, is the following:

```python
import sys
from my_super_app import SpecificAppError
from craft_cli import emit, CraftError, Dispatcher, ArgumentParsingError, ProvideHelpException
...
emit.init(EmitterMode.NORMAL, "my-app-name", f"Starting super app v3")
...
try:
    dispatcher = Dispatcher("my-app-name", COMMAND_GROUPS, summary="What's the app about")
    dispatcher.pre_parse_args(sys.argv[1:])
    dispatcher.load_command(None)
    retcode = dispatcher.run()
except ArgumentParsingError as err:
    print(err, file=sys.stderr)  # to stderr, as argparse normally does
    emit.ended_ok()
    retcode = 1
except ProvideHelpException as err:
    print(err, file=sys.stderr)  # to stderr, as argparse normally does
    emit.ended_ok()
    retcode = 0
except SpecificAppError as err:
    emit.error(err)
    retcode = err.retcode
except KeyboardInterrupt as exc:
    error = CraftError("Interrupted.")
    error.__cause__ = exc
    emit.error(error)
    retcode = 1
except Exception as exc:
    error = CraftError(f"Application internal error: {exc!r}") 
    error.__cause__ = exc
    emit.error(error)
    retcode = 1
else:
    emit.ended_ok()
    if retcode is None:
        retcode = 0
sys.exit(retcode)
```

Both `ArgumentParsingError` and `ProvideHelpException` handling just presents the message to standard error and finishes `emit` ok. Also if there was a problem with the arguments the return code is `1`, but if help was provided, as this the normal result if the user requested for help, the return code is `0`.

Note that this handling of `ArgumentParsingError` allows for the command itself to run this specific exception at run time, in those cases where there is a problem in the arguments presented that cannot be properly handled by the command's declared parsing rules.

The `SpecificAppError` is also handled, and just its message is emitted. This SpecificAppError should inherit `CraftError`, which will provide all its functionality (see [here](FIXME)).

Finally, the `KeyboardInterrupt` exception is handled separatedly to just inform the use that the application was interrputed.


## Defining commands

The `BaseCommand` class is the base to build application commands. All application commands need to subclass it and define some attributes and methods to provide the specific command's functionality.

These are the attributes:

- `name` [mandatory]: the name of the command, its identifier, how the user will refer to it in the command line
- `help_msg` [mandatory]: a one line help for when building application or command specific documentation
- `overview` [mandatory]: a longer multi-line text with the whole command description (also for documentation)
- `common` [optional, defaults to False]: if it's a common/starter command, which are prioritized in the help texts

There are two commands for the subclass to provide:

- `fill_parser`: it will receive an argument parser to be used to specify the command's specific parameters (each command parameters are independent of other commands, but note there are some global ones that are handled automatically by the Dispatcher); if this method is not overridden, the command will not have any specific parameters.

- `run`: execute the command's actual functionality; it will receive the parsed arguments that were defined in `fill_parser`, and should return None or the desired process' return code; this method *must* be overriden in the subclass.

The following is an example of a command that receives a mandatory filepath parameter and removes it, returning a return code that reflects if it run correctly:


```python
import pathlib
import textwrap
from craft_cli import BaseCommand

class RemoveFileCommand(BaseCommand):
    """Remove the indicated file."""

    name = "unlink"
    help_msg = "Remove the indicated file."
    overview = textwrap.dedent("""
        Remove the indicated file.

        A file needs to be indicated. It is an argument error if the path does not exist
        or it's a directory.

        It will return succesfully if the file was properly removed.
    """)

    def fill_parser(self, parser):
        """Add own parameters to the general parser."""
        parser.add_argument("filepath", type=pathlib.Path, help="The file to be removed")

    def run(self, parsed_args):
        """Run the command."""
        if not parsed_args.filepath.exists() or parsed_args.filepath.is_dir():
            raise ArgumentParsingError("The indicated path is not a file or does not exist.")
        try:
            parsed_args.filepath.unlink()
        except Exception as exc:
            emit.message(f"Problem removing the file: {exc}.")
            rc = 1
        else:
            emit.message("File removed succesfully.")
            rc = 0
        return rc
```

Some details to note from the examples's code:
- of course the class subclasses `BaseCommand`
- the overview text is written inside the class, but note it's dedented (so in the help messages starts at without spaces at the left); an alternative is to write the overview text in a variable at module's level and use it from the class attribute
- the `fill_parser` method is overwritten to declare the `filepath` argument, which is specific to this command
- the command execution, in the `run` method, also validates extra argument's particularities (in case of a problem there it would raise `ArgumentParsingError`)

Finally, remember that to be available to the user, the command's class name must be declared in the command groups indicated to Dispatcher (see [this section](FIXME) for more details).


## Running commands

Running an application that uses the `Dispatcher` functionality from the `craft-cli` library is really running a *command* of the application.

In other words, all the application specific functionality will be provided through commands (implemented as described [in this section](FIXME)), and the Dispatcher will be the mechanism to parse the command line arguments given by the user and execute a command if any was indicated, after several verifications (e.g. that the arguments are valid for the command).

The Dispatcher itself also provides some automatic properties for the application (for free, no need for the developer to write any code for these). One is a `help` command, which allows the user to ask for help using the `<app> help` or `<app> help <command>` forms. 

The other is global arguments handling: some options will be recognized and used no matter the position in the command line because they are not specific to any command, but global to all commands and the application itself. So, for example, all these application executions are equivalent:

    <app> --verbose <command> <command-parameter>
    <app> <command> --verbose <command-parameter>
    <app> <command> <command-parameter> --verbose

Dispatcher automatically provides the following global arguments, but more can be specified through the `extra_global_args` option, as explained later):

- `-q` / `--quiet`: sets the `emit` output level to QUIET
- `-v` / `--verbose`: sets the `emit` output level to VERBOSE
- `-t` / `--trace`: sets the `emit` output level to TRACE
- `-h` / `--help`: provides a help text for the application or command

The usage of `Dispatcher` involves several steps that allow to implement application specific features:

FIXME: review these from the REAL BBRANCH

- the instantiation itself, to get a dispatcher instance to work with: `Dispatcher(command_groups, extra_global_options) -> a dispatcher instance` (the command groups and extra global options definition is explained later in this section)

- pre-parsing the user indicated arguments: `dispatcher.pre_parse_args(args) -> global_args`; the provided args are the arguments to the application execution (normally `sys.args[1:]`), and the resulting `global_args` is a dictionary with the all global arguments (e.g. `{'help': False, 'verbose': False, ...}`), very useful for the application to react on those arguments before going on (specially if some extra global options wre indicated).

- loading the command: `dispatcher.load_command(config) -> command`; the configuration passed here will be accesible by the command (`None` can be indicated if the application doesn't have the concept of configuration), and the command instance itself is returned.

- the execution of the command: `dispatcher.run() -> retcode`; the resulting return code is what is indicated by the command, normally used to finish the application process itself (see [this section](FIXME) for more details on how it can be used).

  
FIXME:
- command groups
- extra_global_args

# Collect commands in different groups, for easier human consumption. Note that this is not
# declared in each command because it's much easier to do this separation/grouping in one
# central place and not distributed in several classes/files. Also note that order here is
# important when listing commands and showing help.


The following is a comprehensive example that shows the definition of some command groups, extra global options, and a Dispatcher usage involving those:

FIXME



## Raising errors

FIXME: CraftError can be used directly, or inherited to provide different application errors (which can be handled differntly in the `try/except` section [explained before](FIXME).
FIXME: different attribs and meaning


## Presenting messages to the user

The main interface for the application to emit messages is the `emit` object. It handles everything that goes to screen and to the log file, even interfacing with the formal logging infrastructure to get messages from it.

It's a singleton, just import it wherever it needs to be used:

```python
from craft_cli import emit
```

Before using it, though, it must be initiated. It's simple:

```python
emit.init(mode, appname, greeting, log_filepath)
```

The parameters are:

- mode: the verboseness level for the system to start with (see later in this section about posible values); note that the user can change the level later using global arguments when executing the application, but this is the application default level, very useful if some environment variable needs to be respected in this regard (e.g. `DEBUG=1`)

- appname: the application name for identification purposes

- greeting: a greeting message that will be always logged and shown in the screen in the more verbose modes, very useful to indicate the running version of the application

- log_filepath: a `pathlib.Path` object if a specific log filepath is needed; by default `craft-cli` will manage it, creating it in the user's log directory, and removing old ones to keep just the more recent ones.
        
The values for `mode` are the following attributes of the `EmitterMode` enumerator:

- EmitterMode.QUIET (to present only error messages)
- EmitterMode.NORMAL (error and info messages, with nice progress indications)
- EmitterMode.VERBOSE (for more verbose outputs, including timestamps on each line)
- EmitterMode.TRACE (to also present debug-specific messages)

After bootstrapping the library as shown before, and importing `emit` wherever is needed, all the usage is just sending information to the user. The following sections describe the different ways of doing that.


### Regular messages

The `message` metod is for the final output of the running command.

If there is important information that needs to be shown to the user in the middle of the execution (and not overwritten by other messages) this method can be also used but passing `intermediate=True`.

```python
    def message(self, text: str, intermediate: bool = False) -> None:
```

E.g.:

```python
emit.message("The meaning of life is 42.")
```


### Progress messages

The `progress` method is for all the progress messages intended to provide information that the machinery is running and doing what. 

Messages shown this way are ephemeral in `QUIET` or `NORMAL` modes (overwritten by the next line) and will be truncated to the terminal's width in that case.

```python
    def progress(self, text: str) -> None:
```

E.g.:

```python
emit.progress("Assembling stuff...")
```

### Progress bar

The `progress_bar` method is to be used in a potentially long-running single step of a command (e.g. a download or provisioning step).

It receives a `text` that should reflect the operation that is about to start, a `total` that will be the number to reach when the operation is completed, and optionally a `delta=False` to indicate that calls to `.advance` method should pass the total so far (by default is True, which implies that calls to `.advance` indicates the delta in the operation progress). Returns a context manager with a  `.advance` method to call on each progress.

```python
    def progress_bar(self, text: str, total: Union[int, float], delta: bool = True) -> _Progresser:
```

E.g.:

```python
hasher = hashlib.sha256()
with emit.progress_bar("Hashing the file...", filepath.stat().st_size) as progress:
    with filepath.open("rb") as fh:
        while True:
            data = fh.read(65536)
            hasher.update(data)
            progress.advance(len(data))
            if not data:
                break
```


### Trace/debug messages

The `trace` method is to present all the messages that may used by the *developers* to do any debugging on the application behaviour and/or logs forensics.

```python
    def trace(self, text: str) -> None:
```

E.g.:

```python
emit.trace(f"Hash calculated correctly: {hash_result}")
```


### Get messages from subprocesses

The `open_stream` returns a context manager that can be used to get the standard output and/or error from the executed subprocess. 

This way all the outputs of the subprocess will be captured by `craft-cli` and shown or not to the screen (according to verbosity setup) and always logged.


```python
    def open_stream(self, text: str) -> _StreamContextManager:
```

E.g.:

```python
with emit.open_stream("Running ls") as stream:
    subprocess.run(["ls", "-l"], stdout=stream, stderr=stream)
```


### How to easily test different combinations

There is a collection of examples in the project, in the `examples.py` file.

To run them using the library, a virtualenv needs to be setup:

    python3 -m venv env
    env/bin/pip install -e .[dev]
    source env/bin/activate

After that, is just a matter of running the file specifying which example to use:

    ./examples.py 18

We encourage you to adapt/improve/hack the examples in the file to play with different combinations of message types to learn and "feel" how the output would be in the different cases.


# Documentation

The documentation is in Read The Docs, [check it out](https://craft-cli.readthedocs.io).
FIXME: check what is built


# Contributing

A `Makefile` is provided for easy interaction with the project. To see
all available options run:

    make help


## Running tests

To run all tests in the suite run:

    make tests


## Verifying documentation changes

To locally verify documentation changes run:

    make docs

After running, newly generated documentation shall be available at
`./docs/_build/html/`.


# License

Free software: GNU Lesser General Public License v3
