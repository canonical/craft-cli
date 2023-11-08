import datetime

project = "Craft CLI"
author = "Canonical Group Ltd"
html_title = project + " documentation"
copyright = "%s, %s" % (datetime.date.today().year, author)

ogp_site_url = "https://canonical-craft-cli.readthedocs-hosted.com/"
ogp_site_name = project
ogp_image = "https://assets.ubuntu.com/v1/253da317-image-document-ubuntudocs.svg"

html_context = {
    "product_page": "github.com/canonical/craft-cli",
    "github_url": "https://github.com/canonical/craft-cli",
}

linkcheck_ignore = ["craft_cli.dispatcher.html#craft_cli.dispatcher.CommandGroup"]

# Add extensions
extensions = [
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.coverage",
    "sphinx.ext.doctest",
    "sphinx.ext.autodoc",
    "sphinx_toolbox",
    "canonical_sphinx",
]

# Type hints configuration
set_type_checking_flag = True
typehints_fully_qualified = False
always_document_param_types = True
typehints_document_rtype = True

github_username = "canonical"
github_repository = "craft-cli"

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
