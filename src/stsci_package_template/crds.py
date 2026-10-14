import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import nox

CRDS_RETRIES = 8
CRDS_TIMEOUT = 10


def crds_server_url(observatory: str) -> str:
    """Return the CRDS server URL for an observatory."""
    if not re.fullmatch(r"[a-z0-9]+", observatory):
        msg = f"Invalid CRDS observatory: {observatory!r}"
        raise ValueError(msg)

    return f"https://{observatory}-crds.stsci.edu"


def latest_crds_context(observatory: str) -> str:
    """
    Query the CRDS server for the latest context of an observatory.

    Parameters
    ----------
    observatory :
        The CRDS observatory name (e.g. ``jwst`` or ``roman``).

    Returns
    -------
        The name of the latest CRDS context.

    """
    request = urllib.request.Request(  # noqa: S310
        f"{crds_server_url(observatory)}/json/",
        data=json.dumps(
            {
                "jsonrpc": "1.0",
                "method": "get_default_context",
                "params": [observatory, "latest"],
                "id": 1,
            }
        ).encode(),
        method="POST",
    )

    for attempt in range(CRDS_RETRIES):
        try:
            return _post_json_rpc(request)
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2**attempt)

    return _post_json_rpc(request)


def _post_json_rpc(request: urllib.request.Request) -> str:
    with urllib.request.urlopen(request, timeout=CRDS_TIMEOUT) as response:  # noqa: S310
        return json.load(response)["result"]


def run_crds_context(session: nox.Session) -> None:
    """
    Get the latest CRDS context for the observatory given as the first posarg.

    In GitHub Actions this writes ``context=<context>`` to ``GITHUB_OUTPUT``;
    otherwise the result is logged. An observatory of ``none`` yields an empty
    context.

    Parameters
    ----------
    session :
        The nox session object.

    """
    if len(session.posargs) != 1:
        session.error("Usage: nox -s crds-context -- <observatory>")

    observatory = session.posargs[0]
    context = "" if observatory == "none" else latest_crds_context(observatory)

    if output_path := os.environ.get("GITHUB_OUTPUT"):
        with Path(output_path).open("a", encoding="utf-8") as output_file:
            output_file.write(f"context={context}\n")
    else:
        session.log(f"context={context}")
