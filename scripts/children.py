import os
from pathlib import Path

import requests

GH_TOKEN = os.getenv("GH_TOKEN")

response = requests.get(
    "https://api.github.com/search/code?q=spacetelescope/stsci-package-template+org:spacetelescope+path:.cruft.json",
    headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "Authorization": f"Bearer {GH_TOKEN}",
    },
)


child_repos = [repo["full_name"] for repo in response.json()["items"]]

with open(Path(__file__).parent.parent / "children.txt", "w") as children_file:
    children_file.writelines(child_repos)
