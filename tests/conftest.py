from typing import Any
from unittest.mock import MagicMock, call, create_autospec

import nox
import pytest


@pytest.fixture(params=("uv", "virtualenv"))
def venv(request: pytest.FixtureRequest) -> str:
    """Provide the supported Nox virtual environment backends."""
    return request.param


@pytest.fixture
def session(venv: str) -> MagicMock:
    """Create a mock session based on a venv backend."""
    session = create_autospec(nox.Session, instance=True, spec_set=True)
    session.venv_backend = venv
    session.virtualenv.location = "/path/to/venv"
    return session


@pytest.fixture
def list_dependencies_call(venv: str) -> Any:
    """Return the expected pip-list command for the selected Nox backend."""
    if venv == "uv":
        return call("uv", "pip", "list", "--python", "/path/to/venv", external=True)
    return call("python", "-m", "pip", "list")
