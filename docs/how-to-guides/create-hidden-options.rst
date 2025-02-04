.. _create_hidden_options:

Have a hidden option in a command
=================================

To have a command with an option that should not be shown in the help messages, effectively hidden from final users (e.g. because it's experimental), just use a special value in the option's ``help``::

    def fill_parser(self, parser):
        ...
        parser.add_argument("--experimental-behaviour", help=craft_cli.HIDDEN)
