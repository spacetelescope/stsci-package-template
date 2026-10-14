"""Unit tests for the pytest session helper."""

import argparse
import json
from pathlib import Path
from typing import Any, Literal
from unittest.mock import MagicMock, call, create_autospec

import pytest

from stsci_package_template.dependencies import PythonSupport
from stsci_package_template.pytest import (
    MatrixEntry,
    default_ci_matrix,
    run_check_labels,
    run_coverage_report,
    run_pytest,
    run_tagged_ci,
    run_tests,
)


def test_run_pytest_without_parser(
    session: MagicMock, list_dependencies_call: Any
) -> None:
    """Run tests with default settings when no parser is supplied."""
    session.posargs = ["--coverage", "--develop", "--oldest", "-k", "example"]

    run_pytest(session)

    # Without a parser, posargs are ignored entirely: no options, no passthrough args.
    session.install.assert_called_once_with(".[test]")
    assert session.run.call_args_list == [
        list_dependencies_call,
        call("pytest"),
    ]


@pytest.mark.parametrize("extra", [[], ["-k", "example"]])
@pytest.mark.parametrize("coverage", [False, True])
@pytest.mark.parametrize("dependency", [None, "--develop", "--oldest"])
@pytest.mark.parametrize("install", [None, "--editable", "--wheel"])
@pytest.mark.parametrize("xdist", [None, "--xdist", "--xdist=4"])
def test_run_pytest(
    request: pytest.FixtureRequest,
    session: MagicMock,
    venv: str,
    list_dependencies_call: Any,
    xdist: str | None,
    install: str | None,
    dependency: str | None,
    coverage: bool,
    extra: list[str],
) -> None:
    """Test every valid combination of options."""
    if dependency == "--oldest" and venv != "uv":
        # session.error exits in real nox, so the test is expected to abort with
        # the error rather than reach the assertions.
        session.error.side_effect = RuntimeError("--oldest requires the uv backend")
        request.applymarker(
            pytest.mark.xfail(raises=RuntimeError, strict=True, reason="needs uv")
        )

    # Build the CLI arguments from the selected option combination.
    posargs = [flag for flag in (xdist, dependency) if flag]
    if install == "--wheel":
        posargs += ["--wheel", "pkg.whl"]
    elif install:
        posargs.append(install)
    if coverage:
        posargs.append("--coverage")
    # Extra args are unknown to the parser and must be forwarded to pytest.
    session.posargs = posargs + extra

    run_pytest(session, argparse.ArgumentParser())

    # Install args are ordered: dependency flags, then the package spec, then xdist.
    expected_install: list[str] = []
    if dependency == "--develop":
        expected_install += ["-r", "requirements-dev.txt"]
    elif dependency == "--oldest":
        expected_install += ["--resolution", "lowest-direct"]
    if install == "--wheel":
        expected_install.append("pkg.whl[test]")
    elif install == "--editable":
        expected_install += ["-e", ".[test]"]
    else:
        expected_install.append(".[test]")
    if xdist:
        expected_install.append("pytest-xdist>=3.7")

    # pytest-cov is installed in a separate call after the package install.
    expected_installs = [call(*expected_install)]
    if coverage:
        expected_installs.append(call("pytest-cov>=7.1"))
    assert session.install.call_args_list == expected_installs

    # Pytest args are ordered: xdist, coverage, then the forwarded extra args.
    expected_pytest: list[str] = []
    if xdist:
        expected_pytest += ["-n", "4" if xdist == "--xdist=4" else "auto"]
    if coverage:
        expected_pytest += [
            "--cov=.",
            "--cov-config=pyproject.toml",
            "--cov-report=term-missing",
            "--cov-report=xml",
        ]
    expected_pytest += extra
    # The dependency listing always runs before pytest itself.
    assert session.run.call_args_list == [
        list_dependencies_call,
        call("pytest", *expected_pytest),
    ]


@pytest.mark.parametrize(
    ("posargs", "venv", "exception"),
    [
        pytest.param(
            ["--editable", "--wheel", "pkg.whl"],
            "uv",
            SystemExit,
            id="editable-and-wheel",
        ),
        pytest.param(["--develop", "--oldest"], "uv", SystemExit, id="develop-oldest"),
        pytest.param(["--xdist=abc"], "uv", SystemExit, id="xdist-not-int"),
        pytest.param(["--wheel"], "uv", SystemExit, id="wheel-no-value"),
        pytest.param(["--oldest"], "virtualenv", RuntimeError, id="oldest-needs-uv"),
    ],
)
def test_run_pytest_invalid(
    session: MagicMock,
    posargs: list[str],
    exception: type[BaseException],
) -> None:
    """Test that invalid option combinations fail without running pytest."""
    # Argparse rejects bad options with SystemExit; the uv check goes through
    # session.error, which is mocked to raise so the failure is observable.
    session.posargs = posargs
    session.error.side_effect = RuntimeError("--oldest requires the uv backend")

    with pytest.raises(exception):
        run_pytest(session, argparse.ArgumentParser())

    session.run.assert_not_called()


@pytest.mark.parametrize(
    ("posargs", "expected_python", "expected_posargs"),
    [
        pytest.param(
            ["3.12", "-k", "example"],
            "3.12",
            ["-k", "example"],
            id="explicit-python-version",
        ),
        pytest.param(
            ["-k", "example"],
            "3.13",
            ["-k", "example"],
            id="default-python-version",
        ),
    ],
)
def test_run_tests(
    session: MagicMock,
    posargs: list[str],
    expected_python: str,
    expected_posargs: list[str],
) -> None:
    """Select the requested or default Python version for the test session."""
    session.posargs = posargs.copy()
    python_support = create_autospec(PythonSupport, instance=True)
    python_support.all_versions = ("3.12", "3.13")
    python_support.default.name = "3.13"

    run_tests(session, python_support, "test")

    session.log.assert_called_once_with(f"Target Python interpreter: {expected_python}")
    session.notify.assert_called_once_with("test-" + expected_python, expected_posargs)


@pytest.fixture(
    params=[
        pytest.param(
            ({}, "test-3.13", "", "nox -s test-3.13"),
            id="defaults",
        ),
        pytest.param(
            (
                {"options": ("coverage", "editable")},
                "test-3.13--coverage-editable",
                "coverage-editable",
                "nox -s test-3.13 -- --coverage --editable",
            ),
            id="flags",
        ),
        pytest.param(
            (
                {"options": (("xdist", "4"),)},
                "test-3.13--xdist",
                "xdist",
                "nox -s test-3.13 -- --xdist=4",
            ),
            id="valued-option",
        ),
        pytest.param(
            (
                {
                    "options": ("coverage", ("xdist", "auto")),
                    "runs_on": MatrixEntry.MACOS_RUNS_ON,
                    "tags": ("ci", "test"),
                    "labels": ("full-test", "macos"),
                },
                "test-3.13--coverage-xdist--macos-latest",
                "coverage-xdist",
                "nox -s test-3.13 -- --coverage --xdist=auto",
            ),
            id="mixed-options-and-metadata",
        ),
    ]
)
def matrix_entry_params(
    request: pytest.FixtureRequest,
) -> tuple[dict[str, Any], str, str, str]:
    """Provide the matrix entry case parameters."""
    return request.param


@pytest.fixture
def matrix_entry(
    matrix_entry_params: tuple[dict[str, Any], str, str, str],
) -> MatrixEntry:
    """Build the matrix entry for the selected case."""
    kwargs, _, _, _ = matrix_entry_params
    return MatrixEntry(session="test", python="3.13", **kwargs)


@pytest.fixture
def matrix_entry_expected(
    matrix_entry_params: tuple[dict[str, Any], str, str, str],
) -> dict[str, Any]:
    """Provide the independently specified workflow values for the case."""
    kwargs, name, options, command = matrix_entry_params
    return {
        "name": name,
        "python": "3.13",
        "options": options,
        "nox": command,
        "runs_on": kwargs.get("runs_on", "ubuntu-latest"),
        "labels": list(kwargs.get("labels", ())),
    }


class TestMatrixEntry:
    """Test matrix identifiers, Nox parameters, and workflow output."""

    def test_nox_session(self, matrix_entry: MatrixEntry) -> None:
        """Combine the session name and Python version."""
        assert matrix_entry.nox_session == "test-3.13"

    def test_options_id(
        self, matrix_entry: MatrixEntry, matrix_entry_expected: dict[str, Any]
    ) -> None:
        """Identify options by their names without their values."""
        assert matrix_entry.options_id == matrix_entry_expected["options"]

    def test_nox_id(
        self, matrix_entry: MatrixEntry, matrix_entry_expected: dict[str, Any]
    ) -> None:
        """Include options and non-default runners in parameter identifiers."""
        assert matrix_entry.nox_id == matrix_entry_expected["name"]

    def test_cli_invoke(
        self, matrix_entry: MatrixEntry, matrix_entry_expected: dict[str, Any]
    ) -> None:
        """Represent the Nox command as executable arguments."""
        assert matrix_entry.cli_invoke == tuple(matrix_entry_expected["nox"].split())

    def test_cli_options(
        self, matrix_entry: MatrixEntry, matrix_entry_expected: dict[str, Any]
    ) -> None:
        """Return only the options passed after the Nox argument separator."""
        expected_command = tuple(matrix_entry_expected["nox"].split())
        expected_options = expected_command[4:] if "--" in expected_command else ()

        assert matrix_entry.cli_options == expected_options

    def test_param(
        self, matrix_entry: MatrixEntry, matrix_entry_expected: dict[str, Any]
    ) -> None:
        """Preserve the entry, identifier, and tags in the Nox parameter."""
        parameter = matrix_entry.param

        assert parameter.args == (matrix_entry,)
        assert parameter.id == matrix_entry_expected["name"]
        assert parameter.tags == list(matrix_entry.tags)

    def test_run_session(
        self,
        matrix_entry: MatrixEntry,
        matrix_entry_expected: dict[str, Any],
        session: MagicMock,
    ) -> None:
        """Run Nox with the command arguments and external execution enabled."""
        matrix_entry.run_session(session)

        session.run.assert_called_once_with(
            *tuple(matrix_entry_expected["nox"].split()), external=True
        )

    def test_github_matrix(
        self,
        matrix_entry: MatrixEntry,
        matrix_entry_expected: dict[str, Any],
        session: MagicMock,
        github_output: Path | None,
    ) -> None:
        """Validate the session and log or append the workflow JSON."""
        matrix_entry.github_matrix(session)

        expected_runs = [
            call("nox", "--usage", "test-3.13", silent=True, external=True)
        ]
        if (
            github_output is None
            and matrix_entry_expected["runs_on"] == MatrixEntry.DEFAULT_RUNS_ON
        ):
            expected_runs.append(
                call(*tuple(matrix_entry_expected["nox"].split()), external=True)
            )
        assert session.run.call_args_list == expected_runs
        if github_output is None:
            session.log.assert_called_once()
            assert json.loads(session.log.call_args.args[0]) == matrix_entry_expected
        else:
            existing, actions = github_output.read_text(encoding="utf-8").splitlines()
            assert existing == "existing=value"
            assert actions.startswith("actions=")
            assert json.loads(actions.removeprefix("actions=")) == matrix_entry_expected
            session.log.assert_not_called()


@pytest.fixture
def ci_python_support() -> PythonSupport:
    """Provide distinct oldest, default, and latest Python versions."""
    support = create_autospec(PythonSupport, instance=True)
    support.all_versions = ("3.12", "3.13", "3.14", "3.15")
    support.oldest.name = "3.12"
    support.default.name = "3.13"
    support.latest.name = "3.15"
    return support


@pytest.mark.parametrize("tags", [(), ("ci", "test")])
@pytest.mark.parametrize(
    ("num_xdist", "xdist_options"),
    [
        pytest.param(None, (), id="default"),
        pytest.param(0, (), id="zero-workers"),
        pytest.param(-1, (), id="negative-workers"),
        pytest.param(1, (("xdist", "1"),), id="one-worker"),
        pytest.param(4, (("xdist", "4"),), id="four-workers"),
        pytest.param("auto", ("xdist",), id="auto-workers"),
    ],
)
def test_default_ci_matrix(
    ci_python_support: PythonSupport,
    tags: tuple[str, ...],
    num_xdist: int | Literal["auto"] | None,
    xdist_options: tuple[str | tuple[str, str], ...],
) -> None:
    """Build ordered special-purpose and per-version entries with shared tags."""
    matrix = default_ci_matrix("test", ci_python_support, tags, num_xdist=num_xdist)

    expected = [
        ("3.12", ("oldest", *xdist_options)),
        ("3.15", ("develop", *xdist_options)),
        ("3.13", ("coverage", *xdist_options)),
        ("3.13", ("editable", *xdist_options)),
        ("3.12", xdist_options),
        ("3.13", xdist_options),
        ("3.14", xdist_options),
        ("3.15", xdist_options),
    ]
    assert len(matrix) == len(expected)
    for parameter, (python, options) in zip(matrix, expected, strict=True):
        entry = MatrixEntry(session="test", python=python, options=options, tags=tags)
        assert parameter.args == (entry,)
        assert parameter.id == entry.nox_id
        assert parameter.tags == list(tags)


@pytest.mark.parametrize("num_xdist", ["invalid", "4", "AUTO", ""])
def test_default_ci_matrix_invalid_xdist(
    ci_python_support: PythonSupport, num_xdist: Any
) -> None:
    """Reject worker strings other than the supported auto setting."""
    with pytest.raises(ValueError, match=f"^Invalid value for num_xdist: {num_xdist}$"):
        default_ci_matrix("test", ci_python_support, (), num_xdist=num_xdist)


@pytest.mark.parametrize("tag", ["ci", "test"])
def test_run_tagged_ci(
    session: MagicMock,
    github_output: Path | None,
    tag: str,
) -> None:
    """Select tagged Nox session names and emit them for GitHub Actions."""
    entries = [
        {"name": "ci", "session": "ci(py='3.12')", "tags": ["ci"]},
        {
            "name": "ci",
            "session": "ci(py='3.13')",
            "tags": ["ci", "test"],
        },
        {"name": "build", "session": "build", "tags": ["build"]},
    ]
    session.run.return_value = json.dumps(entries)

    run_tagged_ci(session, tag)

    session.run.assert_called_once_with(
        "nox",
        "--list",
        "--json",
        "--tags",
        tag,
        external=True,
        silent=True,
    )
    expected = json.dumps(
        [entry["session"] for entry in entries if tag in entry["tags"]]
    )
    if github_output is None:
        session.log.assert_called_once_with(f"nox_sessions={expected}")
    else:
        assert github_output.read_text(encoding="utf-8") == (
            f"existing=value\nnox_sessions={expected}\n"
        )


@pytest.mark.parametrize(
    ("event_name", "pr_labels", "labels", "expected"),
    [
        pytest.param("push", None, [], True, id="push-no-labels"),
        pytest.param("push", None, ["slow"], True, id="push-labels"),
        pytest.param(None, None, ["slow"], True, id="local"),
        pytest.param("pull_request", [], [], True, id="pr-no-labels"),
        pytest.param("pull_request", ["slow"], ["slow"], True, id="pr-match"),
        pytest.param(
            "pull_request_target", ["a", "slow"], ["slow", "b"], True, id="pr-any"
        ),
        pytest.param("pull_request", ["other"], ["slow"], False, id="pr-mismatch"),
        pytest.param("pull_request", [], ["slow"], False, id="pr-unlabeled"),
    ],
)
def test_run_check_labels(
    session: MagicMock,
    github_output: Path | None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    event_name: str | None,
    pr_labels: list[str] | None,
    labels: list[str],
    expected: bool,
) -> None:
    """Decide whether a matrix entry runs based on the pull request labels."""
    if event_name is None:
        monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    else:
        monkeypatch.setenv("GITHUB_EVENT_NAME", event_name)

    event_path = tmp_path / "event.json"
    event = (
        {}
        if pr_labels is None
        else {"pull_request": {"labels": [{"name": name} for name in pr_labels]}}
    )
    event_path.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    session.posargs = [json.dumps({"name": "entry", "labels": labels})]

    run_check_labels(session)

    result = f"run={'true' if expected else 'false'}"
    if github_output is None:
        session.log.assert_called_once_with(result)
    else:
        assert github_output.read_text(encoding="utf-8") == (
            f"existing=value\n{result}\n"
        )


@pytest.mark.parametrize("posargs", [[], ["{}", "{}"]])
def test_run_check_labels_usage(session: MagicMock, posargs: list[str]) -> None:
    """Require exactly one matrix entry argument."""
    session.posargs = posargs
    session.error.side_effect = RuntimeError

    with pytest.raises(RuntimeError):
        run_check_labels(session)


@pytest.mark.parametrize("parallel", [True, False])
@pytest.mark.parametrize("summary", [True, False])
def test_run_coverage_report(
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    parallel: bool,
    summary: bool,
) -> None:
    """Combine only when parallel data exists and append the summary if set."""
    monkeypatch.chdir(tmp_path)
    if parallel:
        (tmp_path / ".coverage.host.1234").touch()

    summary_path = tmp_path / "summary.md"
    if summary:
        summary_path.write_text("existing\n", encoding="utf-8")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    else:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    report = "| Name | Cover |"
    session.run.return_value = report

    run_coverage_report(session)

    session.install.assert_called_once_with("coverage[toml]")
    report_call = call(
        "coverage", "report", "-i", "-m", "--format=markdown", silent=True
    )
    assert session.run.call_args_list == (
        [call("coverage", "combine"), report_call] if parallel else [report_call]
    )
    session.log.assert_called_once_with(report)
    if summary:
        assert summary_path.read_text(encoding="utf-8") == (
            f"existing\n## Coverage Report\n{report}\n"
        )
    else:
        assert not summary_path.exists()
