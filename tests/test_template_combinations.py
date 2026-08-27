from pathlib import Path

import pytest
import tomllib
from cookiecutter.main import cookiecutter

ROOT_DIRECTORY = Path(__file__).parent.parent

COMMON_FILENAMES = [
    ".github/pull_request_template.md",
    ".github/workflows/update.yml",
    ".gitignore",
    "LICENSE.txt",
    "README.md",
]
READTHEDOCS_FILENAMES = [".readthedocs.yaml"]
TOWNCRIER_FILENAMES = [
    "towncrier.toml",
    ".github/workflows/changelog.yml",
]


@pytest.mark.parametrize("manage_changelog_with_towncrier", [False, True])
@pytest.mark.parametrize("publish_docs_to", ["none", "readthedocs.io"])
@pytest.mark.parametrize("task_runner", ["none", "nox", "tox"])
@pytest.mark.parametrize(
    "python_build_backend,python_c_extensions",
    [("hatchling", False), ("setuptools", False), ("setuptools", True)],
)
@pytest.mark.parametrize("crds_observatory", ["none", "roman"])
def test_python_package_template(
    tmp_path,
    manage_changelog_with_towncrier,
    task_runner,
    publish_docs_to,
    python_build_backend,
    python_c_extensions,
    crds_observatory,
):
    project_name = "Python Package Template Test"
    project_description = "this is a test of the Python Package template"

    cookiecutter(
        template=str(ROOT_DIRECTORY / "python-package"),
        output_dir=str(tmp_path),
        no_input=True,
        extra_context={
            "project_name": project_name,
            "project_description": project_description,
            "manage_changelog_with_towncrier": manage_changelog_with_towncrier,
            "publish_docs_to": publish_docs_to,
            "task_runner": task_runner,
            "python_c_extensions": python_c_extensions,
            "python_build_backend": python_build_backend,
            "crds_observatory": crds_observatory,
        },
    )

    expected_package_name = (
        project_name.lower().replace(" ", "_").replace("-", "_").replace("'", "")
    )
    expected_package_dir = tmp_path / expected_package_name
    assert expected_package_dir.exists() and expected_package_dir.is_dir()

    for filename in COMMON_FILENAMES:
        assert (expected_package_dir / filename).exists()

    if manage_changelog_with_towncrier:
        for filename in TOWNCRIER_FILENAMES:
            assert (expected_package_dir / filename).exists()
    else:
        for filename in TOWNCRIER_FILENAMES:
            assert not (expected_package_dir / filename).exists()

    if publish_docs_to == "readthedocs.io":
        for filename in READTHEDOCS_FILENAMES:
            assert (expected_package_dir / filename).exists()
    else:
        for filename in READTHEDOCS_FILENAMES:
            assert not (expected_package_dir / filename).exists()

    if task_runner == "tox":
        assert (expected_package_dir / "tox.toml").exists()
    else:
        assert not (expected_package_dir / "tox.toml").exists()

    if task_runner == "nox":
        assert (expected_package_dir / "noxfile.py").exists()
    else:
        assert not (expected_package_dir / "noxfile.py").exists()

    pyproject_toml_filename = expected_package_dir / "pyproject.toml"

    assert pyproject_toml_filename.exists()

    with open(pyproject_toml_filename, "rb") as pyproject_toml_file:
        pyproject_toml = tomllib.load(pyproject_toml_file)

        assert (
            f"{python_build_backend}.build"
            in pyproject_toml["build-system"]["build-backend"]
        )

        assert pyproject_toml["project"]["name"] == expected_package_name
        assert pyproject_toml["project"]["description"] == project_description

    if python_c_extensions:
        assert (expected_package_dir / "setup.py").exists()
    else:
        assert not (expected_package_dir / "setup.py").exists()


@pytest.mark.parametrize("manage_changelog_with_towncrier", [False, True])
def test_other_package_template(
    tmp_path,
    manage_changelog_with_towncrier,
):
    project_name = "Other Package Template Test"
    project_description = "this is a test of the Other Package template"

    cookiecutter(
        template=str(ROOT_DIRECTORY / "other-package"),
        output_dir=str(tmp_path),
        no_input=True,
        extra_context={
            "project_name": project_name,
            "project_description": project_description,
            "manage_changelog_with_towncrier": manage_changelog_with_towncrier,
        },
    )

    expected_package_name = (
        project_name.lower().replace(" ", "_").replace("-", "_").replace("'", "")
    )
    expected_package_dir = tmp_path / expected_package_name
    assert expected_package_dir.exists() and expected_package_dir.is_dir()

    for filename in COMMON_FILENAMES:
        assert (expected_package_dir / filename).exists()

    if manage_changelog_with_towncrier:
        for filename in TOWNCRIER_FILENAMES:
            assert (expected_package_dir / filename).exists()
    else:
        for filename in TOWNCRIER_FILENAMES:
            assert not (expected_package_dir / filename).exists()
