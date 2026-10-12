"""Unit tests for the stsci_package_template.dependencies module."""

import tomllib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from textwrap import dedent
from types import MappingProxyType
from unittest.mock import MagicMock

import pytest
from packaging.requirements import Requirement
from packaging.specifiers import Specifier, SpecifierSet
from packaging.version import Version

from stsci_package_template import dependencies


class TestVersionSupport:
    """Test version metadata normalization and merging."""

    def test_normalizes_release_date_and_properties(self) -> None:
        """Check normalized release dates and derived version properties."""
        support = dependencies.VersionSupport(
            version=Version("1.2.3"),
            release=datetime(2024, 2, 3, 12, 30, tzinfo=UTC),
        )

        # Notice that the time has been normalized to just the date portion
        assert support.release == datetime(2024, 2, 3, tzinfo=UTC).replace(tzinfo=None)

        # Name is just the string of the version itself
        assert support.name == "1.2.3"

        # The version specifier reflects the minimum version requirement based on the
        #    full version
        assert support.specifier == Specifier(">=1.2.3")

        # The version has a patch component if the micro part is non-zero
        assert support.has_patch
        assert not dependencies.VersionSupport(
            version=Version("1.2"), release=None
        ).has_patch

    @pytest.mark.parametrize(
        ("version", "include_patch", "expected"),
        [
            pytest.param("3.12.4", False, "3.12", id="major-minor-only"),
            pytest.param("3.12.4", True, "3.12.4", id="include-patch"),
            pytest.param("3.13.0rc2", True, "3.13.0rc2", id="include-prerelease"),
        ],
    )
    def test_from_version(
        self, version: str, include_patch: bool, expected: str
    ) -> None:
        """Check major/minor truncation and optional patch or prerelease retention."""
        support = dependencies.VersionSupport.from_version(
            Version(version), include_patch=include_patch
        )

        assert support.version == Version(expected)
        assert support.release is None

    def test_merge_uses_earliest_release(self) -> None:
        """Merge patch releases using the earliest known date, if any."""
        first = dependencies.VersionSupport(
            version=Version("1.2"), release=datetime(2024, 2, 3, tzinfo=UTC)
        )
        second = dependencies.VersionSupport(
            version=Version("1.2"), release=datetime(2024, 1, 3, tzinfo=UTC)
        )

        assert first.merge(second).release == datetime(2024, 1, 3, tzinfo=UTC).replace(
            tzinfo=None
        )
        assert (
            first.merge(
                dependencies.VersionSupport(version=Version("1.2"), release=None)
            ).release
            == first.release
        )
        assert (
            dependencies.VersionSupport(version=Version("1.2"), release=None)
            .merge(dependencies.VersionSupport(version=Version("1.2"), release=None))
            .release
            is None
        )

    def test_merge_rejects_different_versions(self) -> None:
        """Reject merging version support records for different versions."""
        first = dependencies.VersionSupport(version=Version("1.2"), release=None)
        other = dependencies.VersionSupport(version=Version("1.3"), release=None)

        with pytest.raises(ValueError, match="different versions"):
            first.merge(other)


@pytest.fixture
def versions() -> MappingProxyType[Version, dependencies.VersionSupport]:
    """Return several release-dated versions for support tests."""
    today = dependencies._today()
    # Include recent and out-of-window releases to exercise fallback selection.
    return MappingProxyType(
        {
            Version("1.0"): dependencies.VersionSupport(
                version=Version("1.0"), release=today - timedelta(days=900)
            ),
            Version("2.0"): dependencies.VersionSupport(
                version=Version("2.0"), release=today - timedelta(days=400)
            ),
            Version("3.0"): dependencies.VersionSupport(
                version=Version("3.0"), release=today - timedelta(days=100)
            ),
        }
    )


@pytest.fixture
def python_support(
    versions: MappingProxyType[Version, dependencies.VersionSupport],
) -> dependencies.PythonSupport:
    """Create a PythonSupport object with three supported versions."""
    return dependencies.PythonSupport(specifier=SpecifierSet(">=1"), versions=versions)


class TestSupport:
    """Test properties and lower-bound behavior shared by support classes."""

    def test_version_properties(
        self,
        python_support: dependencies.PythonSupport,
        versions: MappingProxyType[Version, dependencies.VersionSupport],
    ) -> None:
        """Check oldest, latest, default, release, and all-version properties."""
        assert python_support.oldest == versions[Version("1.0")]
        assert python_support.release == versions[Version("1.0")].release
        assert python_support.latest == versions[Version("3.0")]
        assert python_support.default == versions[Version("2.0")]
        assert python_support.all_versions == ("1.0", "2.0", "3.0")

    def test_single_version_is_default(self) -> None:
        """Use the only supported version as the default."""
        default = dependencies.VersionSupport.from_version(Version("3.12"))

        assert (
            dependencies.PythonSupport(
                specifier=SpecifierSet(">=3.12"),
                versions=MappingProxyType({default.version: default}),
            ).default
            == default
        )

    def test_min_version_window_uses_recent_releases(
        self,
        python_support: dependencies.PythonSupport,
        versions: MappingProxyType[Version, dependencies.VersionSupport],
    ) -> None:
        """Select recent versions and extend the window to meet the minimum."""
        assert python_support._min_version_window(1, 1) == versions[Version("3.0")]
        assert python_support._min_version_window(1, 2) == versions[Version("2.0")]

    def test_min_version_window_extends_and_warns(
        self,
        python_support: dependencies.PythonSupport,
        versions: MappingProxyType[Version, dependencies.VersionSupport],
    ) -> None:
        """Warn when all available versions still cannot meet the requested count."""
        with pytest.warns(UserWarning, match="Only 3 supported version"):
            result = python_support._min_version_window(1, 4)

        assert result == versions[Version("1.0")]

    @pytest.mark.parametrize(
        ("years", "min_number", "message"),
        [
            pytest.param(0, 1, "years", id="zero-years"),
            pytest.param(1, 0, "min_number", id="zero-minimum-count"),
        ],
    )
    def test_min_version_window_rejects_invalid_values(
        self,
        python_support: dependencies.PythonSupport,
        years: int,
        min_number: int,
        message: str,
    ) -> None:
        """Reject a zero-year window or a zero requested-version count."""
        with pytest.raises(ValueError, match=message):
            python_support._min_version_window(years, min_number)

    def test_min_version_window_rejects_empty_versions(self) -> None:
        """Reject support-window selection when there are no versions."""
        with pytest.raises(ValueError, match="empty version set"):
            dependencies.PythonSupport(
                specifier=SpecifierSet(), versions=MappingProxyType({})
            )._min_version_window(1, 1)

    def test_filter_versions(self, python_support: dependencies.PythonSupport) -> None:
        """Keep only releases matching the requested specifier."""
        assert tuple(python_support._filter_versions(SpecifierSet(">=2"))) == (
            Version("2.0"),
            Version("3.0"),
        )

    def test_bump_support(self, python_support: dependencies.PythonSupport) -> None:
        """Use the minimum release in the selected window as the new lower bound."""
        bumped = python_support.bump_support(1, 1)

        assert bumped.specifier == SpecifierSet(">=3.0")
        assert bumped.all_versions == ("3.0",)

    @pytest.mark.parametrize(
        ("current", "new", "expected"),
        [
            pytest.param(">=1,<5", ">=2", ">=2,<5", id="raise-lower-bound"),
            pytest.param(">=2,<5", ">=1", ">=2,<5", id="keep-stricter-bound"),
            pytest.param(">=1,!=2,<5", ">=3", ">=3,<5", id="drop-obsolete-exclusion"),
        ],
    )
    def test_new_lower_bound(self, current: str, new: str, expected: str) -> None:
        """Narrow lower bounds while preserving relevant upper bounds and exclusions."""
        assert dependencies._Support._new_lower_bound(
            SpecifierSet(current), Specifier(new)
        ) == SpecifierSet(expected)

    @pytest.mark.parametrize(
        ("current", "new", "message"),
        [
            pytest.param(
                ">=1",
                "<2",
                "lower bound",
                id="not-a-lower-bound",
            ),
            pytest.param(
                "~=1.2",
                ">=2",
                "compatibility or equality",
                id="compatibility-specifier",
            ),
            pytest.param(
                ">=1",
                ">=2rc1",
                "prerelease",
                id="prerelease-bound",
            ),
            pytest.param(
                ">=1,<2",
                ">=2",
                "exceeds an existing upper bound",
                id="upper-bound-conflict",
            ),
        ],
    )
    def test_new_lower_bound_rejects_invalid_bounds(
        self, current: str, new: str, message: str
    ) -> None:
        """Reject unsupported operators, special releases, and empty ranges."""
        with pytest.raises(ValueError, match=message):
            dependencies._Support._new_lower_bound(
                SpecifierSet(current), Specifier(new)
            )


@pytest.fixture
def pyproject_path(tmp_path: Path) -> Path:
    """Create a project file with Python and dependency metadata."""
    path = tmp_path / "pyproject.toml"
    path.write_text(
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
            dependencies = ["example-dep>=1,<5", "url-dep @ https://example.org/url-dep.whl"]

            [project.optional-dependencies]
            test = ["example-dep>=2,<5"]
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def mock_response(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[object], MagicMock]:
    """Mock requests.get and return a factory for successful JSON responses."""

    def create_response(payload: object) -> MagicMock:
        response = MagicMock()
        response.json.return_value = payload
        monkeypatch.setattr(
            dependencies.requests, "get", MagicMock(return_value=response)
        )
        return response

    return create_response


@pytest.fixture
def python_org_release_candidate() -> dict[str, object]:
    """Return a published Python release-candidate API entry."""
    return {
        "version": 3,
        "name": "Python 3.13.0rc1",
        "is_published": True,
        "pre_release": True,
        "release_date": "2024-05-01T10:00:00+00:00",
    }


@pytest.fixture
def python_org_releases(
    python_org_release_candidate: dict[str, object],
) -> list[dict[str, object]]:
    """Return stable, candidate, unpublished, and non-Python-3 API entries."""
    return [
        {
            "version": 3,
            "name": "Python 3.12.1",
            "is_published": True,
            "pre_release": False,
            "release_date": "2023-12-08T10:00:00+00:00",
        },
        {
            "version": 3,
            "name": "Python 3.12.2",
            "is_published": True,
            "pre_release": False,
            "release_date": "2024-02-01T10:00:00+00:00",
        },
        python_org_release_candidate,
        {
            "version": 3,
            "name": "Python 3.14.0",
            "is_published": False,
            "pre_release": False,
            "release_date": "2025-10-01T10:00:00+00:00",
        },
        {
            "version": 2,
            "name": "Python 2.7.18",
            "is_published": True,
            "pre_release": False,
            "release_date": "2020-04-20T10:00:00+00:00",
        },
    ]


@pytest.fixture
def python_org_selection_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> dependencies.VersionSupport:
    """Mock six stable Python releases and the next release candidate."""
    stable_versions = MappingProxyType(
        {
            Version(f"3.{minor}"): dependencies.VersionSupport.from_version(
                Version(f"3.{minor}")
            )
            for minor in range(8, 14)
        }
    )
    candidate = dependencies.VersionSupport.from_version(
        Version("3.14.0rc1"), include_patch=True
    )
    monkeypatch.setattr(
        dependencies.PythonSupport,
        "_fetch_from_python_org",
        classmethod(
            lambda cls, specifier: (
                stable_versions,
                MappingProxyType({candidate.version: candidate}),
            )
        ),
    )
    return candidate


@pytest.fixture
def python_org_without_stable_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock Python.org with no matching stable releases or candidates."""
    monkeypatch.setattr(
        dependencies.PythonSupport,
        "_fetch_from_python_org",
        classmethod(
            lambda cls, specifier: (MappingProxyType({}), MappingProxyType({}))
        ),
    )


class TestPythonSupport:
    """Test Python version discovery and pyproject metadata updates."""

    def test_classifiers(self, python_support: dependencies.PythonSupport) -> None:
        """Generate one Python classifier for each supported version."""
        assert python_support.classifiers == (
            "Programming Language :: Python :: 1.0",
            "Programming Language :: Python :: 2.0",
            "Programming Language :: Python :: 3.0",
        )

    def test_new_lower_bound_filters_versions(
        self, python_support: dependencies.PythonSupport
    ) -> None:
        """Filter the supported Python versions using a new lower bound."""
        assert python_support.new_lower_bound(Specifier(">=2")).all_versions == (
            "2.0",
            "3.0",
        )

    def test_new_lower_bound_drops_unsupported_candidate(
        self, python_support: dependencies.PythonSupport
    ) -> None:
        """Discard a release candidate that falls outside the new specifier."""
        support = dependencies.PythonSupport(
            specifier=python_support.specifier,
            versions=python_support.versions,
            release_candidate=dependencies.VersionSupport.from_version(
                Version("1.0rc1"), include_patch=True
            ),
        )

        assert support.new_lower_bound(Specifier(">=2")).release_candidate is None

    def test_update_pyproject(
        self, pyproject_path: Path, python_support: dependencies.PythonSupport
    ) -> None:
        """Replace Python classifiers while preserving unrelated classifiers."""
        python_support.update_pyproject(pyproject_path)
        project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]

        assert project["requires-python"] == ">=1"
        assert [
            classifier
            for classifier in project["classifiers"]
            if classifier.startswith("Programming Language :: Python :: ")
        ] == list(python_support.classifiers)
        assert "Topic :: Scientific/Engineering :: Astronomy" in project["classifiers"]

    def test_update_pyproject_adds_classifiers(
        self, pyproject_path: Path, python_support: dependencies.PythonSupport
    ) -> None:
        """Create a classifiers array when the project does not have one."""
        pyproject_path.write_text(
            '[project]\nrequires-python = ">=1"\n', encoding="utf-8"
        )

        python_support.update_pyproject(pyproject_path)
        project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]

        assert project["classifiers"] == list(python_support.classifiers)

    def test_update_pyproject_is_idempotent(
        self, pyproject_path: Path, python_support: dependencies.PythonSupport
    ) -> None:
        """Avoid changing the file when the requested metadata is already present."""
        python_support.update_pyproject(pyproject_path)
        initial = pyproject_path.read_text(encoding="utf-8")

        python_support.update_pyproject(pyproject_path)

        assert pyproject_path.read_text(encoding="utf-8") == initial

    def test_from_pyproject(self, pyproject_path: Path) -> None:
        """Read the Python version range and supported versions from classifiers."""
        support = dependencies.PythonSupport.from_pyproject(pyproject_path)

        assert support.specifier == SpecifierSet(">=3.11")
        assert support.all_versions == ("3.11", "3.12")

    def test_from_pyproject_without_classifiers_warns(self, tmp_path: Path) -> None:
        """Warn and return no supported versions when classifiers are absent."""
        path = tmp_path / "pyproject.toml"
        path.write_text('[project]\nrequires-python = ">=3.11"\n', encoding="utf-8")

        with pytest.warns(UserWarning, match="No Python classifiers found"):
            support = dependencies.PythonSupport.from_pyproject(path)

        assert not support.versions

    def test_fetch_from_python_org_filters_and_groups_releases(
        self,
        mock_response: Callable[[object], MagicMock],
        python_org_releases: list[dict[str, object]],
    ) -> None:
        """Filter python.org releases and separate stable versions from candidates."""
        response = mock_response(python_org_releases)

        stable, candidates = dependencies.PythonSupport._fetch_from_python_org(
            SpecifierSet(">=3.12")
        )

        response.raise_for_status.assert_called_once_with()
        assert tuple(stable) == (Version("3.12"),)
        assert stable[Version("3.12")].release == datetime(
            2023, 12, 8, tzinfo=UTC
        ).replace(tzinfo=None)
        assert tuple(candidates) == (Version("3.13.0rc1"),)

    def test_fetch_from_python_org_checks_response(
        self, mock_response: Callable[[object], MagicMock]
    ) -> None:
        """Propagate errors from the python.org release API response."""
        response = mock_response([])
        response.raise_for_status.side_effect = dependencies.requests.HTTPError(
            "service unavailable"
        )

        with pytest.raises(
            dependencies.requests.HTTPError, match="service unavailable"
        ):
            dependencies.PythonSupport._fetch_from_python_org(SpecifierSet(">=3.12"))

        response.raise_for_status.assert_called_once_with()

    def test_fetch_from_python_org_rejects_duplicate_candidates(
        self,
        mock_response: Callable[[object], MagicMock],
        python_org_release_candidate: dict[str, object],
    ) -> None:
        """Reject duplicate release-candidate versions in the API response."""
        mock_response([python_org_release_candidate, python_org_release_candidate])

        with pytest.raises(ValueError, match="Duplicate Python release candidate"):
            dependencies.PythonSupport._fetch_from_python_org(SpecifierSet(">=3"))

    def test_from_python_org_keeps_five_latest_and_next_candidate(
        self, python_org_selection_versions: dependencies.VersionSupport
    ) -> None:
        """Keep the five newest stable series and the candidate after them."""
        support = dependencies.PythonSupport.from_python_org(SpecifierSet(">=3.9"))

        assert support.all_versions == ("3.9", "3.10", "3.11", "3.12", "3.13")
        assert support.release_candidate == python_org_selection_versions

    @pytest.mark.usefixtures("python_org_without_stable_releases")
    def test_from_python_org_requires_stable_release(self) -> None:
        """Require at least one matching stable release."""
        with pytest.raises(ValueError, match="No published matching stable"):
            dependencies.PythonSupport.from_python_org(SpecifierSet(">=3.11"))


@pytest.fixture
def pypi_releases() -> dict[str, list[dict[str, object]]]:
    """Return PyPI releases covering valid, yanked, prerelease, and invalid cases."""
    return {
        "releases": {
            "1.2.1": [
                {
                    "yanked": False,
                    "upload_time_iso_8601": "2024-02-01T12:00:00+00:00",
                }
            ],
            "1.2.2": [
                {
                    "yanked": False,
                    "upload_time_iso_8601": "2024-01-01T12:00:00+00:00",
                }
            ],
            "2.0.0rc1": [{"yanked": False}],
            "3.0": [{"yanked": True}],
            "not-a-version": [{"yanked": False}],
            "4.0": [{"yanked": False}],
        }
    }


class TestDependencySupport:
    """Test dependency version discovery and pyproject updates."""

    def test_update_pyproject_main_and_optional_dependencies(
        self, pyproject_path: Path
    ) -> None:
        """Update matching requirements in main and optional dependency lists."""
        support = dependencies.DependencySupport(
            name="example_dep",
            specifier=SpecifierSet(">=3,<5"),
            versions=MappingProxyType({}),
        )

        support.update_pyproject(pyproject_path, None)
        support.update_pyproject(pyproject_path, "test")
        project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]

        assert project["dependencies"][0] == "example-dep<5,>=3"
        assert project["optional-dependencies"]["test"][0] == "example-dep<5,>=3"

    @pytest.mark.parametrize("group", [None, "test"])
    def test_update_pyproject_rejects_url_dependencies(
        self, pyproject_path: Path, group: str | None
    ) -> None:
        """Reject URL requirements in both main and optional dependency lists."""
        if group is not None:
            pyproject_path.write_text(
                pyproject_path.read_text(encoding="utf-8").replace(
                    'test = ["example-dep>=2,<5"]',
                    'test = ["url-dep @ https://example.org/url-dep.whl"]',
                ),
                encoding="utf-8",
            )
        support = dependencies.DependencySupport(
            name="url-dep", specifier=SpecifierSet(">=2"), versions=MappingProxyType({})
        )

        with pytest.raises(ValueError, match="URL dependency"):
            support.update_pyproject(pyproject_path, group)

    def test_update_pyproject_requires_dependency(self, pyproject_path: Path) -> None:
        """Raise an error when the requested dependency is not present."""
        support = dependencies.DependencySupport(
            name="missing", specifier=SpecifierSet(">=2"), versions=MappingProxyType({})
        )

        with pytest.raises(ValueError, match="not found"):
            support.update_pyproject(pyproject_path, None)

    def test_new_lower_bound_filters_versions(
        self, versions: MappingProxyType[Version, dependencies.VersionSupport]
    ) -> None:
        """Retain the dependency name while filtering out unsupported releases."""
        support = dependencies.DependencySupport(
            name="example-dep", specifier=SpecifierSet(">=1"), versions=versions
        )

        narrowed = support.new_lower_bound(Specifier(">=2"))

        assert narrowed.name == "example-dep"
        assert narrowed.all_versions == ("2.0", "3.0")

    def test_from_pypi_filters_versions_and_merges_patch_releases(
        self,
        mock_response: Callable[[object], MagicMock],
        pypi_releases: dict[str, list[dict[str, object]]],
    ) -> None:
        """Filter invalid releases and merge patch releases into a version series."""
        mock_response(pypi_releases)

        support = dependencies.DependencySupport.from_pypi(
            "Example_Dep", SpecifierSet(">=1,<4")
        )

        assert support.name == "Example_Dep"
        assert support.all_versions == ("1.2",)
        assert support.versions[Version("1.2")].release == datetime(
            2024, 1, 1, tzinfo=UTC
        ).replace(tzinfo=None)

    def test_from_pypi_checks_response(
        self, mock_response: Callable[[object], MagicMock]
    ) -> None:
        """Raise HTTP response errors before processing release data."""
        response = mock_response({"releases": {}})

        dependencies.DependencySupport.from_pypi("demo", SpecifierSet())

        response.raise_for_status.assert_called_once_with()

    def test_from_pyproject_parses_requirement_and_canonicalizes_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Parse PEP 508 constraints and query PyPI using a canonicalized name."""
        expected = dependencies.DependencySupport(
            name="demo-package",
            specifier=SpecifierSet(">=2,<5"),
            versions=MappingProxyType({}),
        )
        from_pypi = MagicMock(return_value=expected)
        monkeypatch.setattr(dependencies.DependencySupport, "from_pypi", from_pypi)

        result = dependencies.DependencySupport.from_pyproject("Demo_Package>=2,<5")

        assert result is expected
        from_pypi.assert_called_once_with("demo-package", SpecifierSet(">=2,<5"))


@pytest.fixture
def demo_dependency_support(
    monkeypatch: pytest.MonkeyPatch,
) -> dependencies.DependencySupport:
    """Mock dependency parsing with one reusable demo dependency."""
    support = dependencies.DependencySupport(
        name="demo", specifier=SpecifierSet(">=1"), versions=MappingProxyType({})
    )
    monkeypatch.setattr(
        dependencies.DependencySupport,
        "from_pyproject",
        classmethod(lambda cls, dependency: support),
    )
    return support


@pytest.fixture
def python_project_dependency_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock dependency parsing while preserving names from PEP 508 entries."""

    def from_requirement(
        cls: type[dependencies.DependencySupport], entry: str
    ) -> dependencies.DependencySupport:
        return dependencies.DependencySupport(
            name=Requirement(entry).name,
            specifier=SpecifierSet(">=1"),
            versions=MappingProxyType({}),
        )

    monkeypatch.setattr(
        dependencies.DependencySupport,
        "from_pyproject",
        classmethod(from_requirement),
    )


@pytest.fixture
def python_org_project_support() -> MagicMock:
    """Return Python support data for the python.org loading path."""
    return MagicMock(spec=dependencies.PythonSupport)


@pytest.fixture
def mock_python_org_loader(
    monkeypatch: pytest.MonkeyPatch,
    python_org_project_support: MagicMock,
) -> MagicMock:
    """Mock Python.org loading and return its call recorder."""
    loader = MagicMock(return_value=python_org_project_support)
    monkeypatch.setattr(dependencies.PythonSupport, "from_python_org", loader)
    return loader


@pytest.fixture
def classifier_project_support() -> MagicMock:
    """Return Python support data for loading from local classifiers."""
    return MagicMock(spec=dependencies.PythonSupport)


@pytest.fixture
def mock_classifier_loader(
    monkeypatch: pytest.MonkeyPatch,
    classifier_project_support: MagicMock,
) -> MagicMock:
    """Mock classifier-based Python support loading and return its call recorder."""
    loader = MagicMock(return_value=classifier_project_support)
    monkeypatch.setattr(dependencies.PythonSupport, "from_pyproject", loader)
    return loader


@pytest.fixture
def unchanged_python_project() -> dependencies.PythonProject:
    """Return a Python project whose metadata needs no updates."""
    return dependencies.PythonProject(dependencies=MappingProxyType({}))


@pytest.fixture
def changed_python_project() -> dependencies.PythonProject:
    """Return a Python project with an updateable requires-python field."""
    return dependencies.PythonProject(
        python=dependencies.PythonSupport(
            specifier=SpecifierSet(">=3.11"),
            versions=MappingProxyType(
                {
                    Version("3.11"): dependencies.VersionSupport.from_version(
                        Version("3.11")
                    )
                }
            ),
        ),
        dependencies=MappingProxyType({}),
    )


class TestPythonProject:
    """Test project construction, nested groups, and atomic pyproject updates."""

    def test_from_dependencies_parses_entries(
        self, demo_dependency_support: dependencies.DependencySupport
    ) -> None:
        """Build a project dependency mapping from requirement entries."""
        project = dependencies.PythonProject._from_dependencies(["demo>=1"])
        assert project.dependencies["demo"] is demo_dependency_support

    def test_from_dependencies_rejects_duplicates(
        self, demo_dependency_support: dependencies.DependencySupport
    ) -> None:
        """Reject repeated dependency names in the requirement entries."""
        with pytest.raises(ValueError, match="Duplicate dependency"):
            dependencies.PythonProject._from_dependencies(["demo>=1", "demo>=2"])

    @pytest.mark.usefixtures("python_project_dependency_parser")
    def test_from_pyproject_uses_python_org_and_builds_optional_groups(
        self,
        pyproject_path: Path,
        python_org_project_support: MagicMock,
        mock_python_org_loader: MagicMock,
    ) -> None:
        """Load dependencies and optional groups with Python data from python.org."""
        project = dependencies.PythonProject.from_pyproject(pyproject_path)

        assert project.python is python_org_project_support
        assert project.dependencies["example-dep"].name == "example-dep"
        assert (
            project.optional_dependencies["test"].dependencies["example-dep"].name
            == "example-dep"
        )
        mock_python_org_loader.assert_called_once_with(SpecifierSet(">=3.11"))

    @pytest.mark.usefixtures("python_project_dependency_parser")
    def test_from_pyproject_uses_local_classifiers(
        self,
        pyproject_path: Path,
        classifier_project_support: MagicMock,
        mock_classifier_loader: MagicMock,
    ) -> None:
        """Load Python support from local classifiers without calling python.org."""
        project = dependencies.PythonProject.from_pyproject(
            pyproject_path, use_python_org=False
        )

        assert project.python is classifier_project_support
        mock_classifier_loader.assert_called_once_with(pyproject_path)

    def test_update_is_atomic_and_reports_changes(
        self,
        pyproject_path: Path,
        unchanged_python_project: dependencies.PythonProject,
        changed_python_project: dependencies.PythonProject,
    ) -> None:
        """Return whether an update changed the file and commit changes atomically."""
        assert unchanged_python_project.update(pyproject_path) is False
        assert changed_python_project.update(pyproject_path) is True
        assert (
            tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"][
                "requires-python"
            ]
            == ">=3.11"
        )

    def test_update_pyproject_rejects_python_in_nested_group(self) -> None:
        """Reject attempts to update top-level Python metadata in a nested group."""
        nested = dependencies.PythonProject(
            python=dependencies.PythonSupport(
                specifier=SpecifierSet(">=3.11"), versions=MappingProxyType({})
            ),
            dependencies=MappingProxyType({}),
        )

        with pytest.raises(ValueError, match="Updating python in nested"):
            nested.update_pyproject(None, "test")

    def test_update_pyproject_rejects_nested_optional_dependencies(self) -> None:
        """Reject nested optional dependency groups."""
        nested = dependencies.PythonProject(
            dependencies=MappingProxyType({}),
            optional_dependencies=MappingProxyType(
                {"extra": dependencies.PythonProject(dependencies=MappingProxyType({}))}
            ),
        )

        with pytest.raises(ValueError, match="Updating optional dependencies"):
            nested.update_pyproject(None, "test")


@pytest.fixture
def recursive_spec0_dependency() -> MagicMock:
    """Return a dependency mock that remains the same after a support bump."""
    dependency = MagicMock(spec=dependencies.DependencySupport)
    dependency.bump_support.return_value = dependency
    return dependency


@pytest.fixture
def recursive_spec0_python_support() -> MagicMock:
    """Return a Python support mock that remains the same after a support bump."""
    python = MagicMock(spec=dependencies.PythonSupport)
    python.bump_support.return_value = python
    return python


@pytest.fixture
def recursive_spec0_project(
    recursive_spec0_dependency: MagicMock,
    recursive_spec0_python_support: MagicMock,
) -> dependencies.PythonProject:
    """Return a nested project using the SPEC 0 dependency and Python mocks."""
    optional_project = dependencies.PythonProject(
        dependencies=MappingProxyType({"managed": recursive_spec0_dependency})
    )
    return dependencies.PythonProject(
        python=recursive_spec0_python_support,
        dependencies=MappingProxyType(
            {"managed": recursive_spec0_dependency, "other": recursive_spec0_dependency}
        ),
        optional_dependencies=MappingProxyType({"test": optional_project}),
    )


@pytest.fixture
def mock_spec0_schedule_with_future_entry(
    mock_response: Callable[[object], MagicMock],
) -> None:
    """Mock a schedule containing an active package and a future entry."""
    today = dependencies._today()
    mock_response(
        [
            {
                "start_date": (today - timedelta(days=10)).isoformat(),
                "packages": ["Demo_Package"],
            },
            {
                "start_date": (today + timedelta(days=10)).isoformat(),
                "packages": ["future-package"],
            },
        ]
    )


@pytest.fixture
def mock_spec0_project_loader(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock a Python project loaded for a SPEC 0 update."""
    project = MagicMock(spec=dependencies.PythonProject)
    project.update.return_value = True
    project_loader = MagicMock(return_value=project)
    monkeypatch.setattr(dependencies.PythonProject, "from_pyproject", project_loader)
    return project_loader


@pytest.fixture
def spec0_update_schedule_loader(
    monkeypatch: pytest.MonkeyPatch,
    mock_spec0_project_loader: MagicMock,
) -> MagicMock:
    """Mock the SPEC 0 schedule and update-project collaborators."""
    project = mock_spec0_project_loader.return_value
    support = MagicMock(spec=dependencies.Spec0Support)
    support.update_project.return_value = project
    schedule_loader = MagicMock(return_value=support)
    monkeypatch.setattr(dependencies.Spec0Support, "from_schedule", schedule_loader)
    return schedule_loader


class TestSpec0Support:
    """Test applying current SPEC 0 support requirements to a project."""

    def test_update_project_bumps_managed_dependencies_recursively(
        self,
        recursive_spec0_project: dependencies.PythonProject,
        recursive_spec0_python_support: MagicMock,
        recursive_spec0_dependency: MagicMock,
    ) -> None:
        """Bump Python and managed dependencies, including optional groups."""
        updated = dependencies.Spec0Support(dependencies=("managed",)).update_project(
            recursive_spec0_project
        )

        recursive_spec0_python_support.bump_support.assert_called_once_with(3, 3)
        assert recursive_spec0_dependency.bump_support.call_args_list == [
            ((2, 3),),
            ((2, 3),),
        ]
        assert updated.dependencies["managed"] is recursive_spec0_dependency
        assert updated.dependencies["other"] is recursive_spec0_dependency
        assert (
            updated.optional_dependencies["test"].dependencies["managed"]
            is recursive_spec0_dependency
        )

    def test_update_project_handles_missing_python_and_dependencies(self) -> None:
        """Preserve valid projects that lack Python or optional dependency data."""
        project = dependencies.PythonProject(dependencies=MappingProxyType({}))

        updated = dependencies.Spec0Support(dependencies=()).update_project(project)

        assert updated.python is None
        assert not updated.dependencies
        assert updated.optional_dependencies is None

    @pytest.mark.usefixtures("mock_spec0_schedule_with_future_entry")
    def test_from_schedule_canonicalizes_active_packages(self) -> None:
        """Include active packages using canonical names and skip future entries."""
        support = dependencies.Spec0Support.from_schedule()

        assert support.dependencies == ("demo-package",)

    def test_from_schedule_checks_response(
        self, mock_response: Callable[[object], MagicMock]
    ) -> None:
        """Return an empty dependency list for a successful empty schedule."""
        response = mock_response([])

        support = dependencies.Spec0Support.from_schedule()

        assert support.dependencies == ()
        response.raise_for_status.assert_called_once_with()

    def test_run_update_orchestrates_project_and_schedule(
        self,
        pyproject_path: Path,
        mock_spec0_project_loader: MagicMock,
        spec0_update_schedule_loader: MagicMock,
    ) -> None:
        """Load a project, apply the current schedule, then update the project file."""
        project = mock_spec0_project_loader.return_value
        support = spec0_update_schedule_loader.return_value

        assert dependencies.Spec0Support.run_update(pyproject_path) is True
        mock_spec0_project_loader.assert_called_once_with(pyproject_path)
        spec0_update_schedule_loader.assert_called_once_with()
        support.update_project.assert_called_once_with(project)
        project.update.assert_called_once_with(pyproject_path)


@pytest.fixture
def mock_spec0_session() -> MagicMock:
    """Return a Nox session mock that exits after an applied update."""
    session = MagicMock()
    session.error.side_effect = RuntimeError("update applied")
    return session


@pytest.fixture
def mock_spec0_run_update_not_needed(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock SPEC 0 update discovery when no changes are needed."""
    run_update = MagicMock(return_value=False)
    monkeypatch.setattr(dependencies.Spec0Support, "run_update", run_update)
    return run_update


def test_run_update_spec0_does_not_run_lint_when_unchanged(
    pyproject_path: Path,
    mock_spec0_session: MagicMock,
    mock_spec0_run_update_not_needed: MagicMock,
) -> None:
    """Log when no update is needed without running follow-up commands."""
    dependencies.run_update_spec0(mock_spec0_session, pyproject_path, "pre-commit")

    mock_spec0_run_update_not_needed.assert_called_once_with(pyproject_path)
    mock_spec0_session.log.assert_called_once_with("SPEC 0 update not needed.")
    mock_spec0_session.run.assert_not_called()
    mock_spec0_session.error.assert_not_called()


@pytest.fixture
def mock_spec0_run_update_applied(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock SPEC 0 update discovery when changes are applied."""
    run_update = MagicMock(return_value=True)
    monkeypatch.setattr(dependencies.Spec0Support, "run_update", run_update)
    return run_update


@pytest.mark.parametrize("linting_session", [None, "pre-commit"])
def test_run_update_spec0_stops_after_update(
    pyproject_path: Path,
    mock_spec0_session: MagicMock,
    mock_spec0_run_update_applied: MagicMock,
    linting_session: str | None,
) -> None:
    """Run optional linting and ask for review when an update is applied."""
    with pytest.raises(RuntimeError, match="update applied"):
        dependencies.run_update_spec0(
            mock_spec0_session, pyproject_path, linting_session
        )

    mock_spec0_run_update_applied.assert_called_once_with(pyproject_path)
    mock_spec0_session.log.assert_called_once_with("SPEC 0 update applied.")
    if linting_session:
        mock_spec0_session.run.assert_called_once_with(linting_session)
    else:
        mock_spec0_session.run.assert_not_called()
    mock_spec0_session.error.assert_called_once_with(
        "pyproject.toml was updated, please review and commit the changes."
    )
