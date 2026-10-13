import argparse
import re
import shutil
from pathlib import Path

import nox
from packaging.utils import parse_wheel_filename


def list_dependencies(session: nox.Session) -> None:
    """
    List the packages installed in a session's environment.

    Parameters
    ----------
    session :
        The nox session to list the packages for.

    """
    if session.venv_backend == "uv":
        session.run(
            "uv",
            "pip",
            "list",
            "--python",
            session.virtualenv.location,
            external=True,
        )
    else:
        session.run("python", "-m", "pip", "list")


def run_pre_commit_hooks(session: nox.Session) -> None:
    """
    Run all run all pre-commit hooks using prek.

    Parameters
    ----------
    session :
        The nox session to run the pre-commit hooks in.

    """
    default_args = ("--color", "always", "--all-files", "--show-diff-on-failure")

    # Install prek so we don't have to rely on it being pre-installed
    session.install("prek")

    # Prepare all the pre-commit hooks (install them if necessary)
    session.run("prek", "prepare-hooks")

    # Run all the pre-commit hooks with the specified arguments
    session.run("prek", "run", *(session.posargs or default_args))


def run_build_package(
    session: nox.Session,
    test_session: str,
    parser: argparse.ArgumentParser | None = None,
) -> None:
    """
    Build the sdist and wheel into the selected output directory (default: dist/).

    The test session must accept the ``--wheel`` argument to specify the wheel
    to test. Version-specific Python tags append ``-X.Y`` to its session name.

    Parameters
    ----------
    session :
        The nox session to run the build in.
    test_session :
        The name of the nox session to notify when wheel testing is requested.
    parser :
        The optional argument parser to use for parsing session arguments and
        documenting the build options. If ``None``, the default build is run
        without registering or parsing command-line options.

    """
    args = argparse.Namespace(
        test=False, strict=False, cibuildwheel=False, output="dist"
    )
    test_posargs = []
    if parser is not None:
        parser.add_argument(
            "--output",
            default="dist",
            help="Directory to place the built distributions",
        )
        parser.add_argument(
            "--test",
            action="store_true",
            help="Run the test session installing gwcs from the built wheel",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Enable strict checking of the built distributions with twine",
        )
        parser.add_argument(
            "--cibuildwheel",
            action="store_true",
            help="Build wheels with cibuildwheel for the current host",
        )
        args, test_posargs = parser.parse_known_args(session.posargs)

    # Remove the existing output directory if it exists before building new
    # distributions.
    dist = Path(args.output)
    shutil.rmtree(dist, ignore_errors=True)

    # Install the packages needed for building the distributions.
    build_packages = ["build", "twine"]
    if args.cibuildwheel:
        build_packages.append("cibuildwheel")
    session.install(*build_packages)

    # Build the distributions.
    if args.cibuildwheel:
        session.run("python", "-m", "cibuildwheel", "--output-dir", str(dist))
        session.run("python", "-m", "build", "--sdist", "--outdir", str(dist))
    else:
        session.run("python", "-m", "build", "--outdir", str(dist))

    # Check the built distributions with twine
    session.run(
        "twine",
        "check",
        *(["--strict"] if args.strict else []),
        *(str(p) for p in dist.glob("*")),
    )

    # If requested, run the test session using the built wheel
    if args.test:
        wheels = sorted(dist.glob("*.whl"))
        if not wheels:
            session.error(f"No wheel found in {dist}/ to test")
        wheel = wheels[-1]
        _, _, _, tags = parse_wheel_filename(wheel.name)
        python_versions = {
            f"{match[1]}.{match[2]}"
            for tag in tags
            if (match := re.fullmatch(r"[a-z]+(\d)(\d+)", tag.interpreter))
        }
        target = (
            f"{test_session}-{max(python_versions)}"
            if python_versions
            else test_session
        )
        session.notify(target, posargs=["--wheel", str(wheel), *test_posargs])
