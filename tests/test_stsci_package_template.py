"""Integration tests for the stsci_package_template package using Nox sessions."""

import shutil
import subprocess
import sys
import tomllib
from datetime import timedelta
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock

import pytest
from git import Repo
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

import stsci_package_template
from stsci_package_template import dependencies

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_import():
    assert stsci_package_template


@pytest.fixture
def dependency_noxfile(
    tmp_path: Path, venv: str, request: pytest.FixtureRequest
) -> Path:
    """Create a temporary Nox session that installs the project and lists packages."""
    if venv == "uv" and shutil.which("uv") is None:
        request.node.add_marker(
            pytest.mark.xfail(
                reason="uv backend requires the uv executable", strict=True
            )
        )

    noxfile = tmp_path / "noxfile.py"
    noxfile.write_text(
        dedent(
            f"""
            import nox
            from stsci_package_template.utils import list_dependencies

            @nox.session(
                name="integration-list-dependencies",
                python=None,
                venv_backend={venv!r},
            )
            def integration_list_dependencies(session: nox.Session) -> None:
                session.install({str(PROJECT_ROOT)!r})
                list_dependencies(session)
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return noxfile


def test_list_dependencies(tmp_path: Path, dependency_noxfile: Path) -> None:
    """
    Test the dependency list from an installed package in a Nox session.

    Note that this only can really test if the dependencies that are listed
    in the pyproject.toml file are actually installed in the environment.
    """
    # Keep Nox's virtual environments isolated inside pytest's temporary directory.
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "nox",
            "--noxfile",
            str(dependency_noxfile),
            "--envdir",
            str(tmp_path / ".nox"),
            "--session",
            "integration-list-dependencies",
            "--non-interactive",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    # Include Nox's captured output if setup or package installation fails.
    assert result.returncode == 0, result.stdout + result.stderr

    # Locate pip's table so package names can be checked independently of versions.
    output_lines = result.stdout.splitlines()
    table_header = next(
        (
            index
            for index, line in enumerate(output_lines)
            if line.split()[:2] == ["Package", "Version"]
        ),
        None,
    )
    assert table_header is not None, result.stdout

    # Read only the Package column, stopping when the table ends.
    package_names = set()
    for line in output_lines[table_header + 2 :]:
        columns = line.split()
        try:
            package_name, version, *_ = columns
        except ValueError:
            break
        if version == ">":
            break
        package_names.add(canonicalize_name(package_name))

    # Derive required names from project metadata instead of pinning versions.
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        project = tomllib.load(pyproject_file)["project"]
    expected_packages = {canonicalize_name(project["name"])} | {
        canonicalize_name(Requirement(requirement).name)
        for requirement in project["dependencies"]
    }
    assert expected_packages <= package_names


@pytest.fixture
def pre_commit_noxfile(tmp_path: Path, venv: str) -> Path:
    """Create a temporary Nox session that runs prek in dry-run mode."""
    if venv == "uv" and shutil.which("uv") is None:
        pytest.skip("uv backend requires the uv executable")

    noxfile = tmp_path / "noxfile.py"
    noxfile.write_text(
        dedent(
            f"""
            import nox
            from stsci_package_template.utils import run_pre_commit_hooks

            @nox.session(
                name="integration-run-pre-commit-hooks",
                python=None,
                venv_backend={venv!r},
            )
            def integration_run_pre_commit_hooks(session: nox.Session) -> None:
                session.install({str(PROJECT_ROOT)!r})
                with session.chdir({str(PROJECT_ROOT)!r}):
                    run_pre_commit_hooks(session)
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return noxfile


def test_run_pre_commit_hooks(
    tmp_path: Path, pre_commit_noxfile: Path, request: pytest.FixtureRequest
) -> None:
    """
    Test prek's dry-run from an installed package in a Nox session.

    Note that we are only testing with --dry-run so that no modifications are
    made to the source code when pre-commit hooks are run.
    """
    # Keep Nox's virtual environments isolated inside pytest's temporary directory.
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "nox",
            "--noxfile",
            str(pre_commit_noxfile),
            "--envdir",
            str(tmp_path / ".nox"),
            "--session",
            "integration-run-pre-commit-hooks",
            "--non-interactive",
            "--",
            "--dry-run",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with Repo(PROJECT_ROOT) as repo:
        if repo.index.diff(None) and not repo.index.diff("HEAD"):
            request.node.add_marker(
                pytest.mark.xfail(
                    reason="prek skips hooks when changes are only unstaged",
                    raises=AssertionError,
                    strict=True,
                )
            )
    assert "Dry Run" in result.stdout


@pytest.fixture
def wheel_build_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Prepare a temporary Git project and Noxfile for the wheel integration test."""
    project = tmp_path / "project"
    shutil.copytree(
        PROJECT_ROOT,
        project,
        symlinks=True,
        ignore=shutil.ignore_patterns(
            ".git",
            ".gitignore",
            ".nox",
            ".venv",
            ".pytest_cache",
            ".ruff_cache",
            "__pycache__",
            "dist",
        ),
    )

    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    noxfile = project / "noxfile.py"
    noxfile.write_text(
        dedent(
            f"""
            import argparse
            import sys
            from pathlib import Path

            import nox

            sys.path.insert(0, {str(PROJECT_ROOT / "src")!r})
            from stsci_package_template.utils import run_build_package

            @nox.session(name="build-package", python={python_version!r})
            def build_package(session: nox.Session) -> None:
                run_build_package(session, "wheel-smoke", argparse.ArgumentParser())

            @nox.session(name="wheel-smoke", python={python_version!r})
            def wheel_smoke(session: nox.Session) -> None:
                parser = argparse.ArgumentParser()
                parser.add_argument("--wheel", type=Path, required=True)
                wheel = parser.parse_args(session.posargs).wheel
                session.install(str(wheel))
                session.run("python", "-c", "import stsci_package_template")
            """
        ).lstrip(),
        encoding="utf-8",
    )

    hooks_path = tmp_path / "empty-git-hooks"
    hooks_path.mkdir()
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(hooks_path))
    with Repo.init(project) as repo:
        with repo.config_writer() as config:
            config.set_value("user", "name", "Integration Test")
            config.set_value("user", "email", "integration@example.invalid")
            config.set_value("core", "hooksPath", str(hooks_path))
        repo.git.add(A=True)
        repo.index.commit("Prepare isolated wheel build")

    return project


def test_build_and_install_wheel(tmp_path: Path, wheel_build_project: Path) -> None:
    """Build, validate, and import a wheel in an isolated Nox project."""
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "nox",
            "--noxfile",
            str(wheel_build_project / "noxfile.py"),
            "--envdir",
            str(tmp_path / ".nox"),
            "--session",
            "build-package",
            "--non-interactive",
            "--",
            "--test",
            "--strict",
        ],
        cwd=wheel_build_project,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def spec0_update_pyproject(tmp_path: Path) -> Path:
    """Create a project with Python and dependency requirements for SPEC 0."""
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        dedent(
            """
            [project]
            name = "example"
            requires-python = ">=3.11"
            classifiers = [
              "Programming Language :: Python :: 3.11",
              "Programming Language :: Python :: 3.12",
              "Topic :: Scientific/Engineering :: Astronomy",
            ]
            dependencies = ["example-dep>=1,<5"]

            [project.optional-dependencies]
            test = ["example-dep>=1,<5"]
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return pyproject_path


@pytest.fixture
def mock_spec0_update_apis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock the Python.org, PyPI, and SPEC 0 responses for an update."""
    today = dependencies._today()
    python_releases = [
        {
            "version": 3,
            "name": f"Python 3.{minor}.0",
            "is_published": True,
            "pre_release": False,
            "release_date": (today - timedelta(days=365 * age)).isoformat(),
        }
        for minor, age in ((11, 4), (12, 2), (13, 1), (14, 0))
    ]
    pypi_response = {
        "releases": {
            f"{version}.0": [
                {
                    "yanked": False,
                    "upload_time_iso_8601": (
                        today - timedelta(days=days_ago)
                    ).isoformat(),
                }
            ]
            for version, days_ago in ((1, 4 * 365), (2, 500), (3, 300), (4, 30))
        }
    }
    schedule = [
        {
            "start_date": (today - timedelta(days=1)).isoformat(),
            "packages": ["example-dep"],
        }
    ]
    responses = {
        dependencies.PythonSupport.PYTHON_RELEASE_URL: python_releases,
        dependencies.Spec0Support.SCHEDULE_URL: schedule,
    }

    def get_response(url: str, *, timeout: int) -> MagicMock:
        response = MagicMock()
        response.raise_for_status.return_value = None
        if url in responses:
            response.json.return_value = responses[url]
        elif url.startswith("https://pypi.org/pypi/"):
            response.json.return_value = pypi_response
        else:
            pytest.fail(f"Unexpected API request: {url} (timeout={timeout})")
        return response

    monkeypatch.setattr(dependencies.requests, "get", get_response)


@pytest.mark.usefixtures("mock_spec0_update_apis")
def test_run_update_updates_real_pyproject_and_is_idempotent(
    spec0_update_pyproject: Path,
) -> None:
    """Apply mocked SPEC 0 API data through parsing and TOML update paths."""
    pyproject_path = spec0_update_pyproject

    assert dependencies.Spec0Support.run_update(pyproject_path) is True
    project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]
    assert project["requires-python"] == ">=3.12"
    assert [
        classifier
        for classifier in project["classifiers"]
        if classifier.startswith("Programming Language :: Python ::")
    ] == [
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
    ]
    assert project["dependencies"] == ["example-dep<5,>=2.0"]
    assert project["optional-dependencies"]["test"] == ["example-dep<5,>=2.0"]

    assert dependencies.Spec0Support.run_update(pyproject_path) is False
