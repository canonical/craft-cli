PROJECT=craft_cli
# Define when more than the main package tree requires coverage
# like is the case for snapcraft (snapcraft and snapcraft_legacy):
# COVERAGE_SOURCE="starcraft"
UV_TEST_GROUPS := "--group=dev"
UV_DOCS_GROUPS := "--group=docs"
UV_LINT_GROUPS := "--group=lint" "--group=types"
UV_TICS_GROUPS := "--group=tics"

include common.mk

.PHONY: format
format: format-ruff format-codespell format-prettier  ## Run all automatic formatters

.PHONY: lint
lint: lint-ruff lint-codespell lint-mypy lint-prettier lint-pyright lint-shellcheck lint-docs lint-twine  ## Run all linters

.PHONY: pack
pack: pack-pip  ## Build all packages

# Find dependencies that need installing
APT_PACKAGES :=
ifeq ($(wildcard /usr/include/libxml2/libxml/xpath.h),)
APT_PACKAGES += libxml2-dev
endif
ifeq ($(wildcard /usr/include/libxslt/xslt.h),)
APT_PACKAGES += libxslt1-dev
endif
ifeq ($(wildcard /usr/share/doc/python3-venv/copyright),)
APT_PACKAGES += python3-venv
endif

# Used for installing build dependencies in CI.
.PHONY: install-build-deps
install-build-deps: install-lint-build-deps
ifeq ($(APT_PACKAGES),)
else ifeq ($(shell which apt-get),)
	$(warning Cannot install build dependencies without apt.)
	$(warning Please ensure the equivalents to these packages are installed: $(APT_PACKAGES))
else
	sudo $(APT) install $(APT_PACKAGES)
endif

# If additional build dependencies need installing in order to build the linting env.
.PHONY: install-lint-build-deps
install-lint-build-deps:
