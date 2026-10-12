# https://nox.thea.codes/en/stable/config.html

import argparse
from pathlib import Path

import nox

from stsci_package_template.dependencies import PythonSupport, run_update_spec0
from stsci_package_template.pytest import (
    MatrixEntry,
    default_ci_matrix,
    run_pytest,
    run_tests,
)
from stsci_package_template.utils import run_build_package, run_pre_commit_hooks

# Make nox default to uv if its available, if not fallback on virtualenv
nox.options.default_venv_backend = "uv|virtualenv"


PYTHON_SUPPORT = PythonSupport.from_pyproject("pyproject.toml")


@nox.session(python=PYTHON_SUPPORT.all_versions, reuse_venv=False, default=False)
def pytest(session: nox.Session) -> None:
    """
    Run pytest for the given python versions.

    Note there are several built in command-line options that can be passed to
    this session to simplify the pytest invocation.
    - ``--xdist <num>`` Run tests in parallel using the specified number of using
        pytest-xdist.
    - ``-editable`` Install the package in editable mode before running tests.
        (default is not editable like a normal installation from PyPI)
    - ``--wheel <wheel-file>`` Install the package from the specified wheel file.
        This is mutually exclusive with ``--editable``.
    - ``--coverage`` Enable coverage reporting for the tests.
    - ``--develop`` Install development dependencies before running tests.
    - ``--oldest`` Install the oldest compatible dependencies before running tests.
        This is mutually exclusive with ``--develop``.

    Also note that you can pass any additional command-line arguments after these
    built-in options:
    ```
    nox -s pytest-<python-version> -- <built-in-flags> [additional pytest args]
    ```
    Note that if you can drop the `-<python-version>` from the pytest session name
    if you want to run on all of the supported Python versions sequentially.
    """
    parser = argparse.ArgumentParser(
        prog="nox -s pytest --",
        allow_abbrev=False,
        description="Run the package pytest suite.",
    )
    run_pytest(session, parser)


@nox.session(python=None, default=False)
@nox.parametrize(
    "matrix_entry",
    default_ci_matrix("pytest", PYTHON_SUPPORT, ("ci",), num_xdist="auto"),
)
def ci_tests(session: nox.Session, matrix_entry: MatrixEntry) -> None:
    """Return the CI test matrix."""
    matrix_entry.github_matrix(session)


@nox.session(python=None)
def tests(session: nox.Session) -> None:
    """
    Run the unit tests.

    Quick passthrough to the `pytest` session defined above. If
    no python version is specified, it will run on the default Python as defined
    by the PYTHON_SUPPORT configuration. If there is a specific Python version provided,
    it will run on that specific Python version.

    So
    ```
    nox -s tests
    ```
    Will run on the default Python version, but
    ```
    nox -s tests -- <python-version>
    ```
    Will run on the specified Python version.
    """
    run_tests(session, PYTHON_SUPPORT, "pytest")


@nox.session(name="pre-commit", python=PYTHON_SUPPORT.default.name, default=False)
def pre_commit(session: nox.Session):
    """
    Run all pre-commit hooks.

    Note that you may pass any prek arguments after the session name.
    ```
    nox -s pre-commit -- <prek-args>
    ```
    This will override the default arguments that are normally passed to prek.
    see ``run_pre_commit_hooks`` for what those arguments are.
    """
    run_pre_commit_hooks(session)


@nox.session(name="update-spec0", default=False)
def update_spec0(session: nox.Session):
    """Update the project to the latest SPEC 0."""
    run_update_spec0(session, Path("pyproject.toml"), linting_session="pre-commit")


@nox.session(name="build-package", default=False)
def build_package(session: nox.Session):
    """
    Build the Python package.

    Note that there are several built in flags to the build session.
    - ``--test`` Run the unit tests on the wheels built by this session.
    - ``--strict`` Enable strict checking of the built distributions with twine,
        so that any metadata problems that PyPI will reject are caught here.
    - ``--cibuildwheel`` Build the wheels using cibuildwheel.
    """
    parser = argparse.ArgumentParser(
        prog="nox -s build-package --",
        allow_abbrev=False,
        description="Build the sdist and wheel, optionally testing the wheel.",
    )
    run_build_package(session, "pytest", parser)


@nox.session(
    tags=["all"],
    default=False,
)
def format(session):
    session.install("ruff", "pyrefly")
    session.install("-e", ".[contrib]")
    session.run("ruff", "format", ".")
    session.run("ruff", "check", ".", "--fix")
    session.run("ruff", "check", ".", "--fix", "--select", "I")
    session.run("pyrefly", "check", ".")


@nox.session(
    tags=["all", "test"],
    default=False,
)
def test(session):
    session.install("-e", ".[test]")
    session.install("pytest-xdist")
    session.run("pytest", "-n=auto")


@nox.session(
    name="test-with-coverage",
    tags=["all", "coverage"],
    default=False,
)
def test_with_coverage(session):
    session.install("-e", ".[test]")
    session.run("coverage", "run", "-m", "pytest")
    session.run("coverage", "combine")
    session.run("coverage", "report")
    session.run("coverage", "html")


@nox.session(
    tags=["all", "build"],
    default=False,
)
def build(session):
    session.run("rm", "-rf", "build", external=True)
    session.run("rm", "-rf", "dist", external=True)
    session.install("build")
    session.run("python", "-m", "build")
