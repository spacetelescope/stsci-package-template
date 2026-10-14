"""Unit tests for the stsci_package_template.crds module."""

import io
import json
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from stsci_package_template import crds


@pytest.fixture
def urlopen(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock the CRDS server returning a context."""
    urlopen = MagicMock(
        side_effect=lambda *_, **__: io.BytesIO(b'{"result": "jwst_1234.pmap"}')
    )
    monkeypatch.setattr(crds.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(crds.time, "sleep", MagicMock())
    return urlopen


def test_crds_server_url() -> None:
    assert crds.crds_server_url("jwst") == "https://jwst-crds.stsci.edu"


@pytest.mark.parametrize("observatory", ["", "JWST", "evil.com/x", "jwst?x=1"])
def test_crds_server_url_invalid(observatory: str) -> None:
    with pytest.raises(ValueError, match="Invalid CRDS observatory"):
        crds.crds_server_url(observatory)


def test_latest_crds_context(urlopen: MagicMock) -> None:
    assert crds.latest_crds_context("jwst") == "jwst_1234.pmap"

    request: urllib.request.Request = urlopen.call_args.args[0]
    assert request.full_url == "https://jwst-crds.stsci.edu/json/"
    assert request.get_method() == "POST"
    assert isinstance(request.data, bytes)
    assert json.loads(request.data)["params"] == ["jwst", "latest"]
    assert urlopen.call_args.kwargs == {"timeout": crds.CRDS_TIMEOUT}


def test_latest_crds_context_retries(urlopen: MagicMock) -> None:
    response = urlopen.side_effect
    failures = [urllib.error.URLError("down"), TimeoutError()]
    urlopen.side_effect = [*failures, response()]

    assert crds.latest_crds_context("jwst") == "jwst_1234.pmap"
    assert urlopen.call_count == len(failures) + 1


def test_latest_crds_context_gives_up(urlopen: MagicMock) -> None:
    urlopen.side_effect = urllib.error.URLError("down")

    with pytest.raises(urllib.error.URLError):
        crds.latest_crds_context("jwst")
    assert urlopen.call_count == crds.CRDS_RETRIES + 1


@pytest.mark.parametrize(
    ("observatory", "context"),
    [
        ("jwst", "jwst_1234.pmap"),
        ("romancal", "jwst_1234.pmap"),
        ("hstcal", "jwst_1234.pmap"),
        ("none", ""),
    ],
    ids=["jwst", "romancal", "hstcal", "none"],
)
def test_run_crds_context(
    session: MagicMock,
    urlopen: MagicMock,
    github_output: Path | None,
    observatory: str,
    context: str,
) -> None:
    session.posargs = [observatory]

    crds.run_crds_context(session)

    assert urlopen.called == (observatory != "none")
    if github_output is None:
        session.log.assert_called_once_with(f"context={context}")
    else:
        session.log.assert_not_called()
        assert github_output.read_text(encoding="utf-8") == (
            f"existing=value\ncontext={context}\n"
        )


@pytest.mark.parametrize("posargs", [[], ["jwst", "roman"]])
def test_run_crds_context_usage(session: MagicMock, posargs: list[str]) -> None:
    session.posargs = posargs
    session.error.side_effect = RuntimeError

    with pytest.raises(RuntimeError):
        crds.run_crds_context(session)
