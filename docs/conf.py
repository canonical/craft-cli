# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import os
import sys


sys.path.insert(0, os.path.abspath(".."))

import craft_cli  # noqa: E402

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Craft CLI"
copyright = "2023, Canonical"
author = "Canonical"

release = craft_cli.__version__

# region General configuration
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.coverage",
    "sphinx.ext.doctest",
    "sphinx_design",
    "sphinx_copybutton",
    "sphinx-pydantic",
    "sphinx_toolbox",
    "sphinx.ext.autodoc",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

show_authors = False

# endregion
# region Options for HTML output
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_static_path = ["_static"]
html_css_files = [
    "css/custom.css",
]

# endregion
# region Options for extensions
# Intersphinx extension
# https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html#configuration

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# Type hints configuration
set_type_checking_flag = True
typehints_fully_qualified = False
always_document_param_types = True
typehints_document_rtype = True

# Github config
github_username = "canonical"
github_repository = "craft-cli"
# endregion

# Document class properties before public methods
autodoc_member_order = "bysource"


# region Setup reference generation
def run_apidoc(_):
    from sphinx.ext.apidoc import main
    import os
    import sys

    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    cur_dir = os.path.abspath(os.path.dirname(__file__))
    module = os.path.join(cur_dir, "..", "craft_cli")
    exclude_patterns = ["*pytest_plugin*"]
    main(["-e", "--no-toc", "--force", "-o", cur_dir, module, *exclude_patterns])


def no_namedtuple_attrib_docstring(app, what, name, obj, options, lines):
    """Strips out silly "Alias for field number" lines in namedtuples reference."""
    if len(lines) == 1 and lines[0].startswith("Alias for field number"):
        del lines[:]


def setup(app):
    app.connect("builder-inited", run_apidoc)
    app.connect("autodoc-process-docstring", no_namedtuple_attrib_docstring)


# endregion
