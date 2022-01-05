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
from craft_cli import emit, CraftError
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
- before using anything from the library, the `emit` object needs to be initiated, passing the verboseness mode (see [below](FIXME) for more info about it), the application name, and a greeting message (that will be always logged and shown in the screen in the more verbose modes, very useful to indicate the running version of the application)
- all the application execution is in the `try` block; this section will include all `Dispatcher` usage, as shown below in an expanded example
- on any error, a CraftError is created with a custom message and `emit` is called to present the error situation (to the user, logs, etc), which will close it properly; note the assignment of the original exception to the new error's `__cause__`: it will used to enhance the produced information
- if no problems arised, the `emit` object is ended ok, to properly close the terminal's usage

The application execution involves instantiating and using `Dispatcher`. A simple example is presented here (see the [section below](FIXME) for more info), introducing also the handling of an application's return code:


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

FIXME: the attributes! mandatory and not
FIXME: parse_args
FIXME: run


lass BaseCommand:
    """Base class to build application commands.
    Subclass this to create a new command; the subclass must define the following attributes:
    - name: the identifier in the command line
    - help_msg: a one line help for user documentation
    - overview: a longer multi-line text with the whole command description
    Also it may override the following ones to change their default:
    - common: if it's a common/starter command, which are prioritized in the help (default to
      False)
    - needs_config: will ensure a config is provided when executing the command (default to False)
    It also must/can override some methods for the proper command behaviour (see each
    method's docstring).
    The subclass must be declared in the corresponding section of main.COMMAND_GROUPS,
    and will receive and store this group on instantiation (if overriding `__init__`, the
    subclass must pass it through upwards).
    """

    common = False
    needs_config = False
    name: Optional[str] = None
    help_msg: Optional[str] = None
    overview: Optional[str] = None

    def __init__(self, config: Optional[Dict[str, Any]]):
        self.config = config

        # validate attributes
        mandatory = ("name", "help_msg", "overview")
        for attr_name in mandatory:
            if getattr(self, attr_name) is None:
                raise ValueError(f"Bad command configuration: missing value in '{attr_name}'.")

    def fill_parser(self, parser: "_CustomArgumentParser") -> None:
        """Specify command's specific parameters.
        Each command parameters are independent of other commands, but note there are some
        global ones (see `main.Dispatcher._build_argument_parser`).
        If this method is not overridden, the command will not have any parameters.
        """

    def run(self, parsed_args: argparse.Namespace) -> Optional[int]:
        """Execute command's actual functionality.
        It must be overridden by the command implementation.
        This will receive parsed arguments that were defined in :meth:.fill_parser.
        It should return None or the desired process' return code.
        """
        raise NotImplementedError()



## Running commands

FIXME:
- intro parragraph; this is really about running the application through one command
- calling Dispatcher
    - init
    - pre_parse_args
    - load_command
    - run
- automatic functionality
    - -h, -v, -q
    - help command
- command groups
- extra_global_args


## Raising errors

FIXME: CraftError can be used directly, or inherited to provide different application errors (which can be handled differntly in the `try/except` section explained [above](FIXME).
FIXME: different attribs and meaning


## Presenting messages to the user

FIXME: improve intro here--
The main entry point for its usage is the `emit` object, which will handled all ...FIXME
After bootstrapping the library as shown above, and importing `emit` wherever is needed, all the usage is just sending information to the user. This section describes the different ways of doing that.
-
The main interface for the application to emit messages is the `emit` object.  It handles everything that goes to screen and to the log file, even interfacing with the formal logging infrastructure to get messages from it.

It's a singleton, just import it wherever it needs to be used:

```python
from craft_cli import emit
```
--FIXME


### Understanding verbose levels

FIXME: present the four levels
FIXME: tell they are automatically handled, but needs to be choose one for "emit" (which will allows user to handle env vars, like DEBUG=1, etc)


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

FIXME

```python
    def progress_bar(self, text: str, total: Union[int, float], delta: bool = True) -> _Progresser:
```

        Returns a context manager with a `.advance` method to call on each progress (passing the
        delta progress, unless delta=False here, which implies that the calls to `.advance` should
        pass the total so far).
        """

E.g.:

```python

```



### Trace/debug messages

    - `trace`: for all the messages that may used by the *developers* to do any debugging on
    the application behaviour and/or logs forensics.

FIXME
what is it intended for
how to use it (params explained)
GIF with example

    - `trace`: for all the messages that may used by the *developers* to do any debugging on
    the application behaviour and/or logs forensics.


E.g.:

```python

```

### Get messages from subprocesses

FIXME
what is it intended for
how to use it (params explained)
GIF with example

    def open_stream(self, text: str):
        """Open a stream context manager to get messages from subprocesses."""



E.g.:

```python

```


### How to easily test different combinations

FIXME: examples.py


33444  python3 -m venv env
33445  env/bin/pip install -e .[dev]
33448  source env/bin/activate
33449  make tests
33450  make test-units
33451  ./examples.py 18



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
