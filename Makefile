PROJECT=craft_cli
# Define when more than the main package tree requires coverage
# like is the case for snapcraft (snapcraft and snapcraft_legacy):
# COVERAGE_SOURCE="craft_cli"
UV_TEST_GROUPS := "--group=dev"
UV_DOCS_GROUPS := "--group=docs"
UV_LINT_GROUPS := "--group=lint" "--group=types" $(UV_DOCS_GROUPS)
UV_TICS_GROUPS := "--group=tics"

include common.mk

.PHONY: format
format: format-ruff format-codespell format-prettier format-shfmt format-tombi format-pre-commit  ## Run all automatic formatters

.PHONY: lint
lint: lint-code lint-docs lint-twine lint-uv-lockfile lint-actions  ## Run all linters

.PHONY: lint-code
lint-code: lint-ruff lint-ty lint-codespell lint-prettier lint-shfmt lint-shellcheck lint-tombi  ## Run code-specific linters

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
install-lint-build-deps: install-ty

.PHONY: lint-ty
lint-ty: install-ty
	ty check

.PHONY: install-ty
install-ty:
ifneq ($(shell which ty),)
else ifneq ($(shell which snap),)
	sudo snap install --beta astral-ty
	sudo snap alias astral-ty.ty ty
else ifneq ($(shell which uv),)
	uv tool install ty
endif
