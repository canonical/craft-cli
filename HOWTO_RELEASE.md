# Steps

Release early, release often. Don't be lazy.

To use this doc: just replace X.Y.Z with the major.minor.patch version of
the release. The sequence of commands below should be good to copy and
paste, but please pay attention to details!


## Preparation

- update main and run tests to verify all is green

    git fetch upstream
    git merge upstream/main
    make tests


### if it's a minor release (Z == 0)

- tag `main` with only the minor version:

    git tag X.Y
    git push --tags

- create a new release branch

    git checkout -b release-X.Y

- create release notes after all main changes from last tag

    git log --first-parent main --decorate > release-X.Y.Z.txt

- tag the release (using those release notes)

    git tag -s X.Y.Z
    git push --tags


### if it's a micro release (Z != 0)

- go to the release branch

    git checkout release-X.Y

- cherry pick the needed commits from main:

   git cherry-pick -m 1 COMMIT-HASH
   ...

- create release notes from the selected commits

    git log

- tag the release (using those release notes)

    git tag -s X.Y.Z
    git push --tags


## Check all is ready

- change the version number in `craft_cli/__init__.py`

- build a tarball to test

    rm -rf dist/
    python setup.py sdist bdist_wheel

- try the tarball

    mkdir /tmp/testrelease
    cp dist/craft-cli-X.Y.Z.tar.gz /tmp/testrelease/
    cd /tmp/testrelease/
    deactivate  # to be sure nothing is picked from a previous virtualenv
    tar -xf craft-cli-X.Y.Z.tar.gz
    python3 -m venv env
    env/bin/pip install file:///tmp/testrelease/craft-cli-X.Y.Z
    PYTHONPATH=craft-cli-X.Y.Z env/bin/python -c "
        from craft_cli import EmitterMode, emit
        emit.init(EmitterMode.BRIEF, 'explorator', 'Greetings earthlings')
        emit.message('The meaning of life is 42.')
        "
    deactivate
    cd -


## Release

- release in Github

    xdg-open https://github.com/canonical/craft-cli/tags

    You should see all project tags, the top one should be this release.
    In the menu at right of the tag tag you just created, choose 'create
    release'. Copy the release notes into the release description.

    Attach the `dist/` files

    Click on "Publish release"

- release to PyPI

    fades -d twine -x twine upload --verbose dist/*


## Final details

- commit, push, create a PR for the branch
