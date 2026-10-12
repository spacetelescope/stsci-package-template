"""Unit tests for the stsci_package_template.utils module."""

import argparse
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from stsci_package_template import utils


def test_list_dependencies(session: MagicMock, list_dependencies_call: Any) -> None:
    """Test the helper function to list installed dependencies."""
    utils.list_dependencies(session)

    assert session.run.call_args_list == [list_dependencies_call]


@pytest.mark.parametrize(
    ("posargs", "expected_args"),
    [
        pytest.param(
            ["--fake-flag", "fake-value"],
            ("--fake-flag", "fake-value"),
            id="custom",
        ),
        pytest.param(
            [],
            ("--color", "always", "--all-files", "--show-diff-on-failure"),
            id="default",
        ),
    ],
)
def test_run_pre_commit_hooks(
    session: MagicMock, posargs: list[str], expected_args: tuple[str, ...]
) -> None:
    """Test the helper function to run pre-commit hooks."""
    session.posargs = posargs

    utils.run_pre_commit_hooks(session)

    # This is a tautology with the actual code because it is just checking what
    #   is effectively the exact command passed to `session.install` and `session.run`.
    #   Thus an integration test is included in:
    #       test_stsci_package_template.py::test_run_pre_commit_hooks
    #   though this can only test with the --dry-run flag to avoid modifying files.
    session.install.assert_called_once_with("prek")
    assert session.run.call_args_list == [
        call("prek", "prepare-hooks"),
        call("prek", "run", *expected_args),
    ]


@pytest.fixture
def dist(monkeypatch: pytest.MonkeyPatch, build_dir: str | None) -> MagicMock:
    """Create a mock distribution directory for the selected output path."""
    output_dir = build_dir or "dist"
    dist = MagicMock()
    dist.__str__.return_value = output_dir
    wheel = Path(output_dir) / "package-1.0-py3-none-any.whl"
    archive = Path(output_dir) / "package.tar.gz"
    dist.glob.side_effect = lambda pattern: (
        [wheel] if pattern == "*.whl" else [wheel, archive]
    )
    path_factory = MagicMock(return_value=dist)
    dist.path_factory = path_factory
    monkeypatch.setattr(utils, "Path", path_factory)
    return dist


@pytest.fixture
def rmtree(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Track removal of the distribution directory."""
    rmtree = MagicMock()
    monkeypatch.setattr(utils.shutil, "rmtree", rmtree)
    return rmtree


@pytest.fixture(params=[None, "artifacts"])
def build_dir(request: pytest.FixtureRequest) -> str | None:
    """Provide default and custom build output directories."""
    return request.param


@pytest.mark.parametrize("cibuildwheel", [False, True])
@pytest.mark.parametrize("test", [False, True])
@pytest.mark.parametrize("strict", [False, True])
def test_run_build_package(
    session: MagicMock,
    dist: MagicMock,
    rmtree: MagicMock,
    build_dir: str | None,
    cibuildwheel: bool,
    test: bool,
    strict: bool,
) -> None:
    """Test package build modes and output directories."""
    output_dir = build_dir or "dist"
    wheel = Path(output_dir) / "package-1.0-py3-none-any.whl"
    archive = Path(output_dir) / "package.tar.gz"

    # Build the CLI arguments for this combination of options.
    session.posargs = (["--output", build_dir] if build_dir is not None else []) + [
        flag
        for enabled, flag in [
            (cibuildwheel, "--cibuildwheel"),
            (test, "--test"),
            (strict, "--strict"),
        ]
        if enabled
    ]

    # Attach the side-effect mocks to one parent to capture their shared order.
    call_order = MagicMock()
    call_order.attach_mock(rmtree, "rmtree")
    call_order.attach_mock(session.run, "run")
    call_order.attach_mock(session.notify, "notify")

    # Run the helper with the selected options.
    utils.run_build_package(session, "pytest", argparse.ArgumentParser())

    dist.path_factory.assert_called_once_with(output_dir)

    # Work out the expected tools and build commands for the selected mode.
    expected_packages = ["build", "twine"]
    expected_build_commands = [call("python", "-m", "build", "--outdir", output_dir)]
    if cibuildwheel:
        expected_packages.append("cibuildwheel")
        expected_build_commands = [
            call("python", "-m", "cibuildwheel", "--output-dir", output_dir),
            call("python", "-m", "build", "--sdist", "--outdir", output_dir),
        ]

    # Check installed tools and build/twine command arguments.
    session.install.assert_called_once_with(*expected_packages)
    twine_command = call(
        "twine",
        "check",
        *(["--strict"] if strict else []),
        str(wheel),
        str(archive),
    )
    assert session.run.call_args_list == [*expected_build_commands, twine_command]

    # Ensure cleanup happens first and optional testing is scheduled last.
    rmtree.assert_called_once_with(dist, ignore_errors=True)
    expected_order = [
        call.rmtree(dist, ignore_errors=True),
        *(
            call.run(*command.args, **command.kwargs)
            for command in expected_build_commands
        ),
        call.run(*twine_command.args, **twine_command.kwargs),
    ]
    if test:
        expected_order.append(call.notify("pytest", posargs=["--wheel", str(wheel)]))
        session.notify.assert_called_once_with(
            "pytest", posargs=["--wheel", str(wheel)]
        )
    else:
        session.notify.assert_not_called()
    assert call_order.mock_calls == expected_order


@pytest.mark.usefixtures("rmtree")
@pytest.mark.parametrize(
    ("wheel_names", "target", "selected_wheel"),
    [
        pytest.param(
            [
                "package-1.0-cp314-cp314-macosx_11_0_arm64.whl",
                "package-1.0-cp313-cp313-macosx_11_0_arm64.whl",
            ],
            "wheel-tests-3.14",
            "package-1.0-cp314-cp314-macosx_11_0_arm64.whl",
            id="multiple-cp-wheels",
        ),
        pytest.param(
            ["package-1.0-py313-none-any.whl"],
            "wheel-tests-3.13",
            "package-1.0-py313-none-any.whl",
            id="single-python-tag",
        ),
        pytest.param(
            ["package-1.0-py313.py314-none-any.whl"],
            "wheel-tests-3.14",
            "package-1.0-py313.py314-none-any.whl",
            id="multiple-python-tags",
        ),
        pytest.param(
            ["package-1.0-py3-none-any.whl"],
            "wheel-tests",
            "package-1.0-py3-none-any.whl",
            id="generic-py3-wheel",
        ),
    ],
)
def test_run_build_package_wheel_python_versions(
    session: MagicMock,
    dist: MagicMock,
    build_dir: str | None,
    wheel_names: list[str],
    target: str,
    selected_wheel: str,
) -> None:
    """Test selecting the newest wheel interpreter and forwarding arguments."""
    output_dir = build_dir or "dist"
    wheels = [Path(output_dir) / name for name in wheel_names]
    dist.glob.return_value = wheels
    dist.glob.side_effect = None
    session.posargs = [
        "--cibuildwheel",
        "--test",
        *(["--output", build_dir] if build_dir is not None else []),
        "-k",
        "example",
    ]

    utils.run_build_package(session, "wheel-tests", argparse.ArgumentParser())

    session.notify.assert_called_once_with(
        target,
        posargs=["--wheel", str(Path(output_dir) / selected_wheel), "-k", "example"],
    )


@pytest.mark.usefixtures("rmtree")
def test_run_build_package_without_wheel(session: MagicMock, dist: MagicMock) -> None:
    """Fail clearly when wheel testing is requested but no wheel was built."""
    session.posargs = ["--test"]
    session.error.side_effect = RuntimeError("No wheel found")
    dist.glob.return_value = []
    dist.glob.side_effect = None

    with pytest.raises(RuntimeError, match="No wheel found"):
        utils.run_build_package(session, "pytest", argparse.ArgumentParser())

    session.error.assert_called_once_with(f"No wheel found in {dist}/ to test")
    session.notify.assert_not_called()


@pytest.mark.parametrize("build_dir", [None])
def test_run_build_package_without_parser(
    session: MagicMock, dist: MagicMock, rmtree: MagicMock
) -> None:
    """Build with defaults and no command-line option registration."""
    session.posargs = ["--strict", "--test"]

    utils.run_build_package(session, "pytest")

    session.install.assert_called_once_with("build", "twine")
    assert session.run.call_args_list == [
        call("python", "-m", "build", "--outdir", "dist"),
        call(
            "twine", "check", "dist/package-1.0-py3-none-any.whl", "dist/package.tar.gz"
        ),
    ]
    session.notify.assert_not_called()
    rmtree.assert_called_once_with(dist, ignore_errors=True)
