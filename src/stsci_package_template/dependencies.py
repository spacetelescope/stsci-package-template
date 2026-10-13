from __future__ import annotations

import re
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory
from types import MappingProxyType
from typing import ClassVar, Self

import nox
import requests
import tomlkit
from packaging.requirements import Requirement
from packaging.specifiers import Specifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version


def _date_only_datetime(value: datetime) -> datetime:
    """Return the date at midnight, discarding time and timezone information."""
    return value.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def _today() -> datetime:
    """Return the UTC date at midnight, with no timezone information."""
    return datetime.now(tz=UTC).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class VersionSupport:
    """Class for version support information."""

    version: Version
    """
    The major.minor version of the software component normally

    It can include the patch version, if necessary
    """
    release: datetime | None
    """The release date of the specific version, truncated to date precision."""

    def __post_init__(self) -> None:
        """Dataclass post-initialization to normalize the release date."""
        if self.release is not None:
            object.__setattr__(self, "release", _date_only_datetime(self.release))

    @property
    def name(self) -> str:
        """Return the name of the version, typically major.minor."""
        return str(self.version)

    @property
    def has_patch(self) -> bool:
        """Return True if the version includes a patch component."""
        return len(self.version.release) > 2  # noqa: PLR2004

    @property
    def specifier(self) -> Specifier:
        """Return a Specifier representing the version as a minimum version."""
        return Specifier(f">={self.version}")

    def merge(self, other: VersionSupport) -> VersionSupport:
        """
        Merge this VersionSupport instance with another instance.

        Note we will take the earliest release date when merging.

        Parameters
        ----------
        other :
            Another VersionSupport instance to merge with this one.

        Returns
        -------
            A new VersionSupport instance with the merged version and release date.

        """
        if self.version != other.version:
            msg = (
                "Cannot merge VersionSupport instances with different "
                f"versions: {self.version} != {other.version}"
            )
            raise ValueError(msg)

        if self.release is None and other.release is None:
            release = None
        elif self.release is None:
            release = other.release
        elif other.release is None:
            release = self.release
        else:
            release = min(self.release, other.release)

        return VersionSupport(version=self.version, release=release)

    @classmethod
    def from_version(
        cls,
        version: Version,
        release: datetime | None = None,
        include_patch: bool = False,
    ) -> VersionSupport:
        """
        Create a VersionSupport from a version and a release date.

        Parameters
        ----------
        version :
            The Version object representing the software component version.
        release :
            The release date of the specific version.
        include_patch :
            Whether to include the patch version in the VersionSupport instance.

        Returns
        -------
            A VersionSupport instance with the major.minor
            (or major.minor.patch if include_patch is True) version and release date.

        """
        version_str = f"{version.major}.{version.minor}"
        if include_patch:
            version_str += f".{version.micro}"
            if version.pre is not None:
                version_str += f"{version.pre[0]}{version.pre[1]}"

        return cls(version=Version(version_str), release=release)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Support(ABC):
    """Base class for support information about a software component."""

    specifier: SpecifierSet
    """The specifier for the supported versions."""
    versions: MappingProxyType[Version, VersionSupport]
    """A mapping of all major/minor versions to their support information."""

    @property
    def oldest(self) -> VersionSupport:
        """Return the oldest supported version."""
        return self.versions[min(self.versions)]

    @property
    def release(self) -> datetime | None:
        """Return the release date of the oldest supported version."""
        return self.oldest.release

    @property
    def latest(self) -> VersionSupport:
        """Return the latest supported version."""
        return self.versions[max(self.versions)]

    @property
    def default(self) -> VersionSupport:
        """
        Return the default supported version.

        This is the second latest supported version because the
        latest one may not be supported completely when a new version is
        released.

        This is intended to be the default version used for CI testing

        If there there is only one supported version, it will be returned as the
        default.
        """
        if len(self.versions) == 1:
            return self.versions[next(iter(self.versions))]

        return self.versions[sorted(self.versions)[-2]]

    @property
    def all_versions(self) -> tuple[str, ...]:
        """Return a list of all supported version strings."""
        return tuple(version.name for version in self.versions.values())

    def _min_version_window(self, years: int, min_number: int) -> VersionSupport:
        """
        Return the minimum supported version within the specified release window.

        The window starts ``years * 365`` days before the current date. If it
        contains fewer than ``min_number`` versions, the window is extended to
        include the most recent earlier versions. A warning is raised if fewer
        than ``min_number`` versions are available altogether.

        Parameters
        ----------
        years:
            The number of 365-day years back from now to consider.
        min_number:
            The minimum number of versions to include, extending the window if
            necessary.

        Returns
        -------
            The lowest version in the resulting window.

        """
        if years < 1:
            msg = "years must be at least 1"
            raise ValueError(msg)
        if min_number < 1:
            msg = "min_number must be at least 1"
            raise ValueError(msg)
        if not self.versions:
            msg = "Cannot determine a minimum version from an empty version set"
            raise ValueError(msg)

        now = _today()
        cutoff = now - timedelta(days=365 * years)

        selected: dict[Version, VersionSupport] = {}
        for version, support in self.versions.items():
            if support.release is None:
                continue

            if cutoff < support.release <= now:
                selected[version] = support

        # If the time window contains too few releases, extend it backwards by
        # adding the newest remaining versions. Version ordering is the fallback
        # for entries without release dates.
        for version in sorted(self.versions, reverse=True):
            if len(selected) >= min_number:
                break
            selected.setdefault(version, self.versions[version])

        if len(selected) < min_number:
            warnings.warn(
                f"Only {len(selected)} supported version(s) are available; "
                f"at least {min_number} were requested.",
                stacklevel=2,
            )

        return selected[min(selected)]

    @staticmethod
    def _new_lower_bound(current: SpecifierSet, new: Specifier) -> SpecifierSet:  # noqa: PLR0912
        """
        Narrow the lower bound of the specifier based on the given bound.

        Note:
        * raise an error if the provided bound is not a valid lower bound.
        * raise an error if this Object has compatibility or equality specifiers.
        * raise an error if the proposed or existing specifiers use prerelease,
          development, post-release, or local versions.
        * raise an error if the new lower bound makes the range empty.
        * return the original specifier if the new lower bound does not narrow the
          current specifier.

        Parameters
        ----------
        current:
            The current specifier set representing the existing version constraints.
        new :
            A Specifier representing the new lower bound.

        Returns
        -------
            A new SpecifierSet with the narrowed lower bound.

        """
        # Ensure the provided bound is a lower bound.
        if new.operator not in (">", ">="):
            msg = (
                "The bound must be a lower bound, i.e., '>' or '>='. "
                f"Got {new.operator}"
            )
            raise ValueError(msg)

        # Can only handle simple bounds and exclusions.
        if any(s.operator in ("~=", "==", "===") for s in current):
            msg = (
                "Cannot safely update with compatibility or equality specifiers. "
                f"Got: {current}"
            )
            raise ValueError(msg)

        # Lower-bound simplification assumes ordinary final releases; special
        # release labels have additional matching rules, so refuse them here.
        for specifier in (new, *current):
            version = Version(specifier.version.removesuffix(".*"))
            if (
                version.pre is not None
                or version.dev is not None
                or version.post is not None
                or version.local is not None
            ):
                msg = (
                    "Cannot update lower bounds involving prerelease, dev, "
                    f"post, or local versions. Got {specifier}"
                )
                raise ValueError(msg)

        # Convert the new lower bound to a Version object for comparison.
        new_version = Version(new.version)

        # Check that the new lower bound does not exceed any existing upper bounds.
        for upper in (s for s in current if s.operator in ("<", "<=")):
            upper_version = Version(upper.version)
            if (new_version > upper_version) or (
                new_version == upper_version
                and (new.operator == ">" or upper.operator == "<")
            ):
                msg = (
                    "The new lower bound exceeds an existing upper bound."
                    f"  New lower bound: {new}"
                    f"  Existing upper bound: {upper}"
                )
                raise ValueError(msg)

        # Check that the new lower bound actually narrows the lower bound otherwise
        #    we just return the current specifier set.
        if old_bounds := [s for s in current if s.operator in (">", ">=")]:
            old = max(
                old_bounds,
                key=lambda s: (Version(s.version), s.operator == ">"),
            )
            old_version = Version(old.version)
            if (new_version < old_version) or (
                new_version == old_version
                and old.operator == ">"
                and new.operator == ">="
            ):
                return current

        # Combine the current specifiers together into a new SpecifierSet.
        specifiers = [str(new)]
        for specifier in (s for s in current if s.operator not in (">", ">=")):
            # Check any not equal exclusions to see if they are still valid
            if specifier.operator == "!=":
                # Handle wildcard exclusions (e.g., "!=1.2.*") separately.
                if specifier.version.endswith(".*"):
                    excluded_prefix = Version(specifier.version[:-2])
                    next_release = (
                        *excluded_prefix.release[:-1],
                        excluded_prefix.release[-1] + 1,
                    )
                    epoch = f"{excluded_prefix.epoch}!" if excluded_prefix.epoch else ""
                    next_prefix = Version(
                        f"{epoch}{'.'.join(map(str, next_release))}.dev0"
                    )
                    # The wildcard excludes every release under this prefix. It
                    # is redundant only once the lower bound is beyond that prefix.
                    if new_version >= next_prefix:
                        continue
                else:
                    excluded_version = Version(specifier.version)
                    # If the excluded version is strictly below the new lower bound,
                    #   then it is no longer relevant and can be skipped.
                    # If the excluded version is equal to the new lower bound and
                    #   the new lower bound is strict, then the exclusion is no longer
                    #   relevant and can be skipped.
                    if excluded_version < new_version or (
                        excluded_version == new_version and new.operator == ">"
                    ):
                        continue

            specifiers.append(str(specifier))

        return SpecifierSet(",".join(specifiers))

    def _filter_versions(
        self, specifier: SpecifierSet
    ) -> MappingProxyType[Version, VersionSupport]:
        """
        Filter the versions based on the given specifier set.

        Parameters
        ----------
        specifier :
            The specifier set to filter the versions against.

        Returns
        -------
            A mapping of versions that satisfy the specifier set.

        """
        return MappingProxyType(
            {
                version: support
                for version, support in self.versions.items()
                if version in specifier
            }
        )

    @abstractmethod
    def new_lower_bound(self, new: Specifier) -> Self:
        """
        Return a new instance with the updated lower bound.

        Parameters
        ----------
        new :
            The new lower bound specifier to apply to the instance.

        Returns
        -------
            A new instance of the class with the updated lower bound.

        """

    def bump_support(self, years: int, min_number: int) -> Self:
        """
        Return a new instance with the support bumped by the given number of years.

        Parameters
        ----------
        years :
            The number of years to bump the support by. Must be at least 1.
        min_number :
            The minimum number of versions to retain support for.

        Returns
        -------
            A new instance of the class with the updated support.

        """
        return self.new_lower_bound(
            self._min_version_window(years, min_number).specifier
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PythonSupport(_Support):
    """Information about supported Python versions."""

    PYTHON_MAJOR: ClassVar[int] = 3
    PYTHON_RELEASE_URL: ClassVar[str] = (
        "https://www.python.org/api/v2/downloads/release/"
    )
    PYTHON_RELEASE_PATTERN: ClassVar[re.Pattern] = re.compile(r"Python 3\.(\d+)\.(\d+)")
    PYTHON_CANDIDATE_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"Python 3\.(\d+)\.0rc(\d+)"
    )
    PYTHON_CLASSIFIER_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"Programming Language :: Python :: (\d+\.\d+)"
    )
    release_candidate: VersionSupport | None = None
    """The latest release candidate python version. e.g. 3.15rc2"""

    @property
    def classifiers(self) -> tuple[str, ...]:
        """Classifiers for the supported Python versions."""
        return tuple(
            f"Programming Language :: Python :: {version}"
            for version in sorted(self.versions)
        )

    def _update_classifiers(self, pyproject_path: Path) -> None:
        """
        Update the Python version classifiers in the given pyproject.toml file.

        Parameters
        ----------
        pyproject_path :
            The path to the pyproject.toml file.

        """
        pyproject = tomlkit.parse(pyproject_path.read_text(encoding="utf-8"))
        project = pyproject["project"]
        existing_classifiers = project.get("classifiers", [])
        expected_classifiers = [
            classifier
            for classifier in existing_classifiers
            if not self.PYTHON_CLASSIFIER_PATTERN.fullmatch(classifier)
        ] + list(self.classifiers)

        # Keep the formatter's layout when the classifier values are unchanged.
        if "classifiers" in project and set(existing_classifiers) == set(
            expected_classifiers
        ):
            return

        # Add a classifiers section if it doesn't exist.
        if "classifiers" not in project:
            project["classifiers"] = tomlkit.array().multiline(True)
        classifiers: list[str] = project["classifiers"]

        # Remove existing Python version classifiers.
        for index in range(len(classifiers) - 1, -1, -1):
            if self.PYTHON_CLASSIFIER_PATTERN.fullmatch(classifiers[index]):
                del classifiers[index]

        # Add the new Python version classifiers
        classifiers += self.classifiers

        pyproject_path.write_text(tomlkit.dumps(pyproject), encoding="utf-8")

    def _update_requires_python(self, pyproject_path: Path) -> None:
        """
        Update the requires-python field in the given pyproject.toml file.

        Parameters
        ----------
        pyproject_path :
            The path to the pyproject.toml file.

        """
        pyproject = tomlkit.parse(pyproject_path.read_text(encoding="utf-8"))
        project = pyproject["project"]
        project["requires-python"] = str(self.specifier)
        pyproject_path.write_text(tomlkit.dumps(pyproject), encoding="utf-8")

    def update_pyproject(self, pyproject_path: Path) -> None:
        """
        Update the classifiers and the requires-python field in the pyproject.toml file.

        Parameters
        ----------
        pyproject_path :
            The path to the pyproject.toml file.

        """
        self._update_classifiers(pyproject_path)
        self._update_requires_python(pyproject_path)

    def new_lower_bound(self, new: Specifier) -> PythonSupport:
        """Recast the dependency with a new lower bound."""
        specifier = self._new_lower_bound(self.specifier, new)

        release_candidate = self.release_candidate
        if release_candidate is not None and not specifier.contains(
            str(release_candidate.version), prereleases=True
        ):
            release_candidate = None

        return PythonSupport(
            specifier=specifier,
            versions=self._filter_versions(specifier),
            release_candidate=release_candidate,
        )

    @classmethod
    def from_pyproject(cls, pyproject_path: Path) -> PythonSupport:
        """
        Read the supported Python versions from a pyproject.toml file.

        Note this uses the Classifiers as recommended by nox to make the
        determination. So if that information is missing then we don't list
        any supported Python versions.

        Parameters
        ----------
        pyproject_path :
            The path to the pyproject.toml file.

        Returns
        -------
            An instance of PythonSupport populated with the supported Python versions
            specified in the pyproject.toml file.

        """
        pyproject = nox.project.load_toml(pyproject_path)
        try:
            versions = {}
            for version_str in sorted(nox.project.python_versions(pyproject)):
                version = Version(version_str)
                versions[version] = VersionSupport.from_version(version)
        except ValueError:
            warnings.warn(
                "No Python classifiers found; no supported Python versions detected.",
                stacklevel=2,
            )
            versions = {}

        return cls(
            specifier=SpecifierSet(pyproject["project"]["requires-python"]),
            versions=MappingProxyType(versions),
        )

    @classmethod
    def _fetch_from_python_org(
        cls, specifier: SpecifierSet
    ) -> tuple[
        MappingProxyType[Version, VersionSupport],
        MappingProxyType[Version, VersionSupport],
    ]:
        """
        Fetch the release information from python.org matching the specifier.

        Parameters
        ----------
        specifier :
            The Python version specifier (requires-python from pyproject.toml).

        Returns
        -------
            A tuple containing a mapping of the stable versions and a mapping of
            the release candidate versions matching the specifier.

        """
        # Fetch Python release information from python.org
        response = requests.get(cls.PYTHON_RELEASE_URL, timeout=15)
        response.raise_for_status()

        # Look through the listed releases from the python.org API for what
        # we are interested in.
        stable_versions: dict[Version, VersionSupport] = {}
        release_candidates: dict[Version, VersionSupport] = {}
        for release in response.json():
            # Only consider python 3 releases that are published
            if release.get("version") != cls.PYTHON_MAJOR or not release.get(
                "is_published"
            ):
                continue

            # Extract the full version number from the release name.
            name = release.get("name", "")
            version = Version(name.removeprefix("Python "))

            # Skip versions that do not match the specifier.
            if specifier is not None and not specifier.contains(
                version, prereleases=True
            ):
                continue

            # Match against the stable and release candidate name patterns
            stable_match = cls.PYTHON_RELEASE_PATTERN.fullmatch(name)
            candidate_match = cls.PYTHON_CANDIDATE_PATTERN.fullmatch(name)

            # If no match for either stable or release candidate, skip this release
            if stable_match is None and candidate_match is None:
                continue

            # Add the match if it matches the stable pattern and is not marked
            #   by python as a pre-release.
            if stable_match is not None and not release.get("pre_release"):
                version_support = VersionSupport.from_version(
                    version,
                    release=datetime.fromisoformat(release["release_date"]),
                    include_patch=False,
                )

                # Merge the version support information into the stable versions
                # dictionary.
                if version_support.version in stable_versions:
                    stable_versions[version_support.version] = stable_versions[
                        version_support.version
                    ].merge(version_support)
                else:
                    stable_versions[version_support.version] = version_support

                continue

            # Add the match if it matches the release candidate pattern and is marked
            #   by python as a pre-release.
            if candidate_match is not None and release.get("pre_release"):
                version_support = VersionSupport.from_version(
                    version,
                    release=datetime.fromisoformat(release["release_date"]),
                    include_patch=True,
                )

                # If the release candidate version already exists something has
                #    gone wrong.
                if version_support.version in release_candidates:
                    msg = (
                        "Duplicate Python release candidate "
                        f"version found: {version_support.version}"
                    )
                    raise ValueError(msg)

                release_candidates[version_support.version] = version_support

        return (
            MappingProxyType(stable_versions),
            MappingProxyType(release_candidates),
        )

    @classmethod
    def from_python_org(cls, specifier: SpecifierSet) -> PythonSupport:
        """
        Read from python.org the available and supported Python versions.

        Parameters
        ----------
        specifier :
            The Python version specifier (requires-python from pyproject.toml).

        Returns
        -------
            An instance of PythonSupport populated with the available and supported
            Python versions from python.org.

        """
        stable_versions, release_candidates = cls._fetch_from_python_org(specifier)

        if not stable_versions:
            msg = "No published matching stable Python 3 releases found on python.org"
            raise ValueError(msg)

        # Python's annual minor releases are supported across the latest five series.
        # See https://peps.python.org/pep-0602/#2-years-of-full-support-3-more-years-of-security-fixes
        # for the five-year lifecycle. Current statuses: https://devguide.python.org/versions/
        versions = MappingProxyType(
            {
                version: stable_versions[version]
                for version in sorted(stable_versions)[-5:]
            }
        )

        # Find the release candidate that comes after the latest stable release
        latest_stable = max(stable_versions)
        release_candidate = max(
            (version for version in release_candidates if version > latest_stable),
            default=None,
        )
        return cls(
            specifier=specifier,
            versions=versions,
            release_candidate=(
                None
                if release_candidate is None
                else release_candidates[release_candidate]
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class DependencySupport(_Support):
    """
    Information about the supported versions for a dependency.

    Note that this fundamentally requires accessing PyPi to find all the published
    versions of a dependency.
    """

    PYPI_URL: ClassVar[str] = "https://pypi.org/pypi/{name}/json"
    name: str
    """The name of the dependency."""

    def update_pyproject(self, pyproject_path: Path, group: str | None) -> None:
        """
        Update the specified dependency in the given pyproject.toml file.

        Parameters
        ----------
        pyproject_path :
            The path to the pyproject.toml file.
        group :
            The optional dependency group to update, or None for the main dependencies.

        """
        pyproject = tomlkit.parse(pyproject_path.read_text(encoding="utf-8"))
        project = pyproject["project"]
        dependencies = (
            project["dependencies"]
            if group is None
            else project["optional-dependencies"][group]
        )
        name = canonicalize_name(self.name)
        found = False
        for index, dependency in enumerate(dependencies):
            requirement = Requirement(dependency)
            if canonicalize_name(requirement.name) != name:
                continue
            if requirement.url is not None:
                msg = (
                    "Cannot update version constraints for a URL "
                    f"dependency: {dependency}"
                )
                raise ValueError(msg)
            requirement.specifier = self.specifier
            dependencies[index] = str(requirement)
            found = True

        if not found:
            msg = f"Dependency {self.name!r} not found in dependency group {group!r}"
            raise ValueError(msg)

        pyproject_path.write_text(tomlkit.dumps(pyproject), encoding="utf-8")

    def new_lower_bound(self, new: Specifier) -> DependencySupport:
        """Recast the dependency with a new lower bound."""
        specifier = self._new_lower_bound(self.specifier, new)
        return DependencySupport(
            name=self.name,
            specifier=specifier,
            versions=self._filter_versions(specifier),
        )

    @classmethod
    def from_pypi(cls, name: str, specifier: SpecifierSet) -> DependencySupport:
        """
        Create a DependencySupport instance by querying PyPi for the available versions.

        Fetch the available versions of the specified dependency and filter them
        according to the given specifier.

        Parameters
        ----------
        name :
            The name of the dependency.
        specifier :
            The version specifier to filter the available versions.

        Returns
        -------
            An instance of DependencySupport with the supported versions.

        """
        # Fetch the package information from PyPi
        response = requests.get(cls.PYPI_URL.format(name=name), timeout=15)
        response.raise_for_status()

        versions: dict[Version, VersionSupport] = {}
        for release, files in response.json()["releases"].items():
            try:
                version = Version(release)
            except InvalidVersion:
                continue
            if (
                version.is_prerelease
                or all(file.get("yanked") for file in files)
                or version not in specifier
            ):
                continue

            release_date = min(
                (
                    datetime.fromisoformat(file["upload_time_iso_8601"])
                    for file in files
                    if not file.get("yanked") and file.get("upload_time_iso_8601")
                ),
                default=None,
            )
            version_support = VersionSupport.from_version(
                version,
                release=release_date,
            )
            if version_support.version in versions:
                versions[version_support.version] = versions[
                    version_support.version
                ].merge(version_support)
            else:
                versions[version_support.version] = version_support

        return cls(name=name, specifier=specifier, versions=MappingProxyType(versions))

    @classmethod
    def from_pyproject(cls, dependency: str) -> DependencySupport:
        """
        Create a DependencySupport instance from a PEP 508 dependency entry.

        Parameters
        ----------
        dependency :
            A dependency entry from ``project.dependencies`` or one of the
            ``project.optional-dependencies`` lists in pyproject.toml.

        Returns
        -------
            An instance of DependencySupport for the specified dependency.

        """
        requirement = Requirement(dependency)
        return cls.from_pypi(canonicalize_name(requirement.name), requirement.specifier)


@dataclass(frozen=True, slots=True, kw_only=True)
class PythonProject:
    """Represents the Python project's classifiers and support information."""

    python: PythonSupport | None = None
    """The Python support information for this project"""
    dependencies: MappingProxyType[str, DependencySupport]
    """The dependency support information for this project."""
    optional_dependencies: MappingProxyType[str, PythonProject] | None = None
    """The optional dependency support information for this project."""

    def update_pyproject(self, pyproject_path: Path, group: str | None = None) -> None:
        """
        Update the project's pyproject.toml file to reflect this object's state.

        Note, this is not atomic by default, do not call this directly. It is public
        because it is used recursively on nested PythonProject instances. Instead
        use the `update` method for atomic updates.

        Parameters
        ----------
        pyproject_path :
            The path to the pyproject.toml file.
        group :
            The dependency group to update, or None to update the main dependencies.

        """
        if self.python is not None:
            if group is not None:
                msg = f"Updating python in nested python project for group '{group}'"
                raise ValueError(msg)

            self.python.update_pyproject(pyproject_path)

        for dependency in self.dependencies.values():
            dependency.update_pyproject(pyproject_path, group)

        if self.optional_dependencies is not None:
            if group is not None:
                msg = (
                    "Updating optional dependencies in nested python project "
                    f"for group '{group}'"
                )
                raise ValueError(msg)

            for group_name, project in self.optional_dependencies.items():
                project.update_pyproject(pyproject_path, group_name)

    def update(self, pyproject_path: Path) -> bool:
        """
        Stage updates in a temporary copy and replace the original only if changed.

        Parameters
        ----------
        pyproject_path :
            The path to the pyproject.toml file.

        Returns
        -------
        bool
            True if the file was changed, otherwise False.

        """
        with TemporaryDirectory(dir=pyproject_path.parent) as directory:
            temporary_path = Path(directory) / pyproject_path.name
            copy2(pyproject_path, temporary_path)
            self.update_pyproject(temporary_path)

            if temporary_path.read_bytes() == pyproject_path.read_bytes():
                return False

            temporary_path.replace(pyproject_path)
            return True

    @classmethod
    def _from_dependencies(
        cls,
        dependency_list: list[str],
        python: PythonSupport | None = None,
        optional_dependencies: MappingProxyType[str, PythonProject] | None = None,
    ) -> PythonProject:
        """
        Create a PythonProject instance given a list of dependency strings.

        Parameters
        ----------
        dependency_list :
            A list of dependency strings, typically from the project's
            ``project.dependencies`` or ``project.optional-dependencies``
            in pyproject.toml.
        python :
            The Python support information for the project. If not provided,
            it will be inferred from the dependencies if possible.
        optional_dependencies :
            A dictionary mapping optional dependency names to their corresponding
            PythonProject instances.

        """
        dependencies: dict[str, DependencySupport] = {}
        for dependency in dependency_list:
            support = DependencySupport.from_pyproject(dependency)

            if support.name in dependencies:
                msg = f"Duplicate dependency found: {support.name}"
                raise ValueError(msg)

            dependencies[support.name] = support

        return cls(
            python=python,
            dependencies=MappingProxyType(dependencies),
            optional_dependencies=optional_dependencies,
        )

    @classmethod
    def from_pyproject(
        cls, pyproject_path: Path, use_python_org: bool = True
    ) -> PythonProject:
        """
        Create a PythonProject from a pyproject.toml file.

        Parameters
        ----------
        pyproject_path :
            The path to the pyproject.toml file.

        use_python_org :
            Whether to query the python.org release page for the python versions
            or just use the classifiers specified in the pyproject.toml.

        Returns
        -------
            An instance of PythonProject populated with data from the
            pyproject.toml.

        """
        project = nox.project.load_toml(pyproject_path)["project"]

        if use_python_org:
            python = PythonSupport.from_python_org(
                SpecifierSet(project["requires-python"])
            )
        else:
            python = PythonSupport.from_pyproject(pyproject_path)

        optional_dependencies = MappingProxyType(
            {
                group: cls._from_dependencies(dependencies)
                for group, dependencies in project.get(
                    "optional-dependencies", {}
                ).items()
            }
        )

        return cls._from_dependencies(
            project.get("dependencies", []),
            python=python,
            optional_dependencies=optional_dependencies,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Spec0Support:
    """The minimum dependency versions currently required by SPEC 0."""

    SCHEDULE_URL: ClassVar[str] = (
        "https://github.com/scientific-python/spec0-action/releases/latest/download/schedule.json"
    )
    SPEC_0_PYTHON_WINDOW: ClassVar[int] = 3
    SPEC_0_DEPENDENCY_WINDOW: ClassVar[int] = 2
    MIN_SUPPORT_NUMBER: ClassVar[int] = 3

    dependencies: tuple[str, ...]
    """The list of current SPEC 0 managed dependencies."""

    def update_project(self, project: PythonProject) -> PythonProject:
        """
        Update the given project with the current SPEC 0 minimum dependency versions.

        Parameters
        ----------
        project :
            The Python project to update.

        Returns
        -------
            The updated Python project.

        """
        python = (
            None
            if project.python is None
            else project.python.bump_support(
                self.SPEC_0_PYTHON_WINDOW, self.MIN_SUPPORT_NUMBER
            )
        )
        dependencies = dict(project.dependencies)
        for name, dependency in dependencies.items():
            if name in self.dependencies:
                dependencies[name] = dependency.bump_support(
                    self.SPEC_0_DEPENDENCY_WINDOW, self.MIN_SUPPORT_NUMBER
                )
        optional_dependencies = (
            None
            if project.optional_dependencies is None
            else MappingProxyType(
                {
                    group: self.update_project(dependencies)
                    for group, dependencies in project.optional_dependencies.items()
                }
            )
        )
        return PythonProject(
            python=python,
            dependencies=MappingProxyType(dependencies),
            optional_dependencies=optional_dependencies,
        )

    @classmethod
    def run_update(cls, pyproject_path: Path) -> bool:
        """
        Update the Python project at the given pyproject.toml path to the latest SPEC 0.

        Parameters
        ----------
        pyproject_path :
            The path to the pyproject.toml file of the project to update.

        Returns
        -------
        bool
            True if the project was updated, False otherwise.

        """
        project = PythonProject.from_pyproject(pyproject_path)
        support = cls.from_schedule()
        updated = support.update_project(project)

        return updated.update(pyproject_path)

    @classmethod
    def from_schedule(cls) -> Spec0Support:
        """
        Read the current SPEC 0 minimum versions from the published schedule.

        The schedule is published quarterly by scientific-python as a list of
        entries, each giving the new minimum versions of the packages whose
        support changes on that entry's start date.

        Parameters
        ----------
        packages :
            The package names to look up minimum versions for.

        Returns
        -------
            An instance of Spec0Support populated with the minimum versions of the
            packages which appear in the schedule up to today.

        """
        # Fetch the schedule from the URL
        response = requests.get(cls.SCHEDULE_URL, timeout=15)
        response.raise_for_status()

        now = _today()
        dependencies: set[str] = set()
        for entry in sorted(response.json(), key=lambda entry: entry["start_date"]):
            if _date_only_datetime(datetime.fromisoformat(entry["start_date"])) > now:
                break

            dependencies.update(canonicalize_name(name) for name in entry["packages"])

        return cls(dependencies=tuple(dependencies))


def run_update_spec0(
    session: nox.Session, pyproject_path: Path, linting_session: str | None = None
) -> None:
    """
    Run the SPEC 0 update for the given Python project.

    Parameters
    ----------
    session :
        The nox session to use for running commands.
    pyproject_path :
        The path to the pyproject.toml file of the project to update.
    linting_session :
        The name of the linting session to run after updating.

    """
    if Spec0Support.run_update(pyproject_path):
        session.log("SPEC 0 update applied.")
        if linting_session:
            session.run(linting_session)
        session.error(
            "pyproject.toml was updated, please review and commit the changes."
        )

    session.log("SPEC 0 update not needed.")
