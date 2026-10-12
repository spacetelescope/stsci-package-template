import argparse
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal

import nox

from .dependencies import PythonSupport
from .utils import list_dependencies


def add_standard_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add the standard command-line arguments to the parser.

    Parameters
    ----------
    parser :
        The argument parser to add the standard arguments to.

    """
    parser.add_argument(
        "--xdist",
        nargs="?",
        const=True,
        default=False,
        type=int,
        help="Enable pytest-xdist for parallel test execution",
    )

    # Ensure that only one of --editable or --wheel can be specified
    install_group = parser.add_mutually_exclusive_group()
    install_group.add_argument(
        "--editable",
        action="store_true",
        help="Install package in editable mode",
    )
    install_group.add_argument(
        "--wheel",
        type=Path,
        default=None,
        help="Install package from a built wheel file instead of the source tree",
    )


def install_package(
    session: nox.Session,
    args: argparse.Namespace,
    install_args: list[str] | None = None,
) -> None:
    """
    Install the package in the virtual environment based on the command-line arguments.

    Parameters
    ----------
    session :
        The nox session to install the package in.
    args :
        The parsed command-line arguments.
    install_args :
        Additional arguments to pass to the installation command.

    """
    install_args = install_args or []

    # Setup the install arguments for gwcs itself
    if args.wheel is not None:
        install_args += [f"{args.wheel}[test]"]
    elif args.editable:
        install_args += ["-e", ".[test]"]
    else:
        install_args += [".[test]"]

    session.log("Installing the package for testing:")

    # Add pytest-xdist if requested
    if args.xdist:
        session.log("  Including pytest-xdist for parallel test execution")
        install_args += ["pytest-xdist>=3.7"]

    session.install(*install_args)


def init_pytest_arguments(session: nox.Session, args: argparse.Namespace) -> list[str]:
    """
    Initialize the pytest arguments based on the command-line options.

    Parameters
    ----------
    session :
        The nox session to run pytest in.
    args :
        The parsed command-line arguments.

    Returns
    -------
        The list of arguments to pass to pytest.

    """
    session.log("Running tests:")

    arguments: list[str] = []
    if args.xdist:
        session.log("  Including pytest-xdist for parallel test execution")
        arguments += ["-n", "auto" if args.xdist is True else str(args.xdist)]

    return arguments


def run_pytest(
    session: nox.Session, parser: argparse.ArgumentParser | None = None
) -> None:
    """
    Run the pytest test suite.

    Parameters
    ----------
    session :
        The nox session to run pytest in.
    parser :
        The optional argument parser to use for parsing and documenting
        command-line options. If ``None``, the default test configuration is
        used without registering or parsing command-line options.

    """
    args = argparse.Namespace(
        xdist=False,
        editable=False,
        wheel=None,
        coverage=False,
        develop=False,
        oldest=False,
    )
    pytest_args = []
    if parser is not None:
        add_standard_arguments(parser)

        # Build the parser, adding the options as we go
        parser.add_argument(
            "--coverage",
            action="store_true",
            help="Enable coverage reporting",
        )

        # Ensure that only one of --develop or --oldest can be specified
        dependency_group = parser.add_mutually_exclusive_group()
        dependency_group.add_argument(
            "--develop",
            action="store_true",
            help="Install development dependencies",
        )
        dependency_group.add_argument(
            "--oldest",
            action="store_true",
            help="Install the oldest compatible dependencies",
        )
        args, pytest_args = parser.parse_known_args(session.posargs)
    install_args: list[str] = []

    # Prepare the install arguments for dev/oldest if required
    if args.develop:
        install_args += ["-r", "requirements-dev.txt"]
    if args.oldest:
        if session.venv_backend != "uv":
            session.error("--oldest requires the uv backend")

        install_args += ["--resolution", "lowest-direct"]

    install_package(session, args, install_args)

    # Install coverage if requested
    if args.coverage:
        session.log("Installing coverage dependencies:")
        session.install("pytest-cov>=7.1")

    list_dependencies(session)

    # Configure the pytest arguments
    arguments = init_pytest_arguments(session, args)
    if args.coverage:
        session.log("  Enabling coverage reporting")
        arguments += [
            "--cov=.",
            "--cov-config=pyproject.toml",
            "--cov-report=term-missing",
            "--cov-report=xml",
        ]
    arguments += pytest_args

    session.run("pytest", *arguments)


def run_tests(
    session: nox.Session, python_support: PythonSupport, run_session: str
) -> None:
    """
    Run the specified test session for the given Python support.

    Parameters
    ----------
    session : nox.Session
        The Nox session object.
    python_support : PythonSupport
        The Python support configuration.
    run_session : str
        The name of the session to run.

    """
    if session.posargs and session.posargs[0] in python_support.all_versions:
        target_python = session.posargs.pop(0)
    else:
        target_python = python_support.default.name

    session.log(f"Target Python interpreter: {target_python}")
    session.notify(f"{run_session}-{target_python}", session.posargs)


@dataclass(frozen=True, slots=True, kw_only=True)
class MatrixEntry:
    """
    Represents an entry in a github workflow job matrix.

    Note that this is to represent something like:
    ```
    nox -s <session>-<python> -- [options]
    ```
    """

    DEFAULT_RUNS_ON: ClassVar[str] = "ubuntu-latest"
    MACOS_RUNS_ON: ClassVar[str] = "macos-latest"

    session: str
    """The name of the session that will execute this matrix entry."""
    python: str
    """The Python version for this matrix entry."""
    options: tuple[str | tuple[str, str], ...] = field(default_factory=tuple)
    """
    The options for this matrix entry

    Each option can be either a string or a tuple of two strings.
    -> A single string will be used as `--option` in the nox command.
    -> A tuple of two strings will be used as `--option=value` in the nox command.
    """
    runs_on: str = field(default=DEFAULT_RUNS_ON)
    """The runner environment for this matrix entry."""
    tags: tuple[str, ...] = field(default_factory=tuple)
    """
    The the nox tags for this matrix entry
    """
    labels: tuple[str, ...] = field(default_factory=tuple)
    """
    The GitHub labels for this matrix entry.

    If empty, then this entry will always run regardless of labels applied.
    If non-empty, run this entry only if the PR has any of the specified labels.
    """

    @property
    def nox_session(self) -> str:
        """
        The nox session name for this matrix entry.

        This is what one should use to run the session:
        ```
        nox -s {self.nox_session}
        ```
        """
        return f"{self.session}-{self.python}"

    @property
    def options_id(self) -> str:
        """
        The ID representing the options for this matrix entry.

        This is a string that uniquely identifies the combination of options.
        """
        return "-".join(
            f"{opt[0]}" if isinstance(opt, tuple) else opt for opt in self.options
        )

    @property
    def nox_id(self) -> str:
        """The shorthand parameter id for nox parameterization."""
        nox_id = f"{self.session}-{self.python}"
        if self.options:
            nox_id += f"--{self.options_id}"
        if self.runs_on != self.DEFAULT_RUNS_ON:
            nox_id += f"--{self.runs_on}"
        return nox_id

    @property
    def param(self) -> nox.param:
        """
        The nox parameter for this matrix entry.

        This is used for nox parameterization.
        """
        return nox.param(
            self,
            id=self.nox_id,
            tags=self.tags or None,
        )

    @property
    def cli_options(self) -> tuple[str, ...]:
        """
        The CLI options for this matrix entry.

        This is a string that represents the options to pass to the CLI.
        """
        return tuple(
            f"--{opt[0]}={opt[1]}" if isinstance(opt, tuple) else f"--{opt}"
            for opt in self.options
        )

    @property
    def cli_invoke(self) -> tuple[str, ...]:
        """
        The CLI command to invoke this matrix entry.

        This is what one should use to run the session with nox:
        ```
        nox -s {self.nox_session} -- <options>
        ```
        """
        command = ["nox", "-s", self.nox_session]

        if self.cli_options:
            command.append("--")
            command.extend(self.cli_options)

        return tuple(command)

    def run_session(self, session: nox.Session) -> None:
        """
        Run the nox session for this matrix entry.

        This will invoke the session with the appropriate CLI options.
        """
        # Use session.run instead of session.notify to ensure that every session is
        #    actually run. Notify just adds the session under its session name to the
        #    session queue if it is not already in the queue. There is also no way
        #    to wait until the notify session has completed. Using session.run ensures
        #    that the session execution pauses right here until its execution is
        #    complete.
        session.run(*self.cli_invoke, external=True)

    def github_matrix(self, session: nox.Session) -> None:
        """
        Write the GitHub matrix entry to the ``actions`` workflow output.

        Log the entry when running outside GitHub Actions. And then run the
        session if its on the default runs_on environment.
        """
        # Check if the nox_session is even properly defined by running
        #   `nox --usage <session>`
        # We know that nox exists, because we are running via nox
        session.run(
            "nox",
            "--usage",
            self.nox_session,
            silent=True,
            external=True,
        )

        actions = json.dumps(
            {
                "name": self.nox_id,
                "python": self.python,
                "options": self.options_id,
                "nox": " ".join(self.cli_invoke),
                "runs_on": self.runs_on,
                "labels": self.labels,
            }
        )
        if output_path := os.environ.get("GITHUB_OUTPUT"):
            with Path(output_path).open("a", encoding="utf-8") as output:
                output.write(f"actions={actions}\n")
        else:
            session.log(actions)

            if self.runs_on == self.DEFAULT_RUNS_ON:
                self.run_session(session)


def default_ci_matrix(
    session: str,
    python_support: PythonSupport,
    tags: tuple[str, ...],
    *,
    num_xdist: int | Literal["auto"] | None = None,
) -> list[nox.param]:
    """
    Return the default CI matrix for the given Python support.

    This includes the oldest, latest, and default Python versions with appropriate
    options.

    Note that this assumes that the session you are running on supports
        --oldest
        --develop
        --coverage
        --editable
    flags

    Parameters
    ----------
    session :
        The nox session name.
    python_support :
        The Python support information.
    tags :
        The tags to apply to each matrix entry.
    num_xdist :
        The number of xdist workers to add to the matrix entries.
        If non-positive, then no xdist workers are added.
        If None, no xdist workers are added.
        If "auto", then the number of xdist workers is determined automatically.

    Returns
    -------
        The list of nox parameters representing the CI matrix.

    """
    if num_xdist is None or (not isinstance(num_xdist, str) and num_xdist <= 0):
        xdist_options = ()
    elif isinstance(num_xdist, str):
        if num_xdist != "auto":
            msg = f"Invalid value for num_xdist: {num_xdist}"
            raise ValueError(msg)

        xdist_options = ("xdist",)
    else:
        xdist_options = (("xdist", str(num_xdist)),)

    return [
        MatrixEntry(
            session=session,
            python=python_support.oldest.name,
            options=("oldest", *xdist_options),
            tags=tags,
        ).param,
        MatrixEntry(
            session=session,
            python=python_support.latest.name,
            options=("develop", *xdist_options),
            tags=tags,
        ).param,
        MatrixEntry(
            session=session,
            python=python_support.default.name,
            options=("coverage", *xdist_options),
            tags=tags,
        ).param,
        MatrixEntry(
            session=session,
            python=python_support.default.name,
            options=("editable", *xdist_options),
            tags=tags,
        ).param,
        *[
            MatrixEntry(
                session=session,
                python=python,
                options=xdist_options,
                tags=tags,
            ).param
            for python in python_support.all_versions
        ],
    ]
