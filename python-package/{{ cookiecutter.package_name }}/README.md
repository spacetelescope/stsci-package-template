<a href="https://stsci.edu">
  <img src="https://github.com/spacetelescope/stsci-package-template/blob/0c4b13779e02ff9b8fb3585615e26d51cadcc14b/docs/_static/stsci_pri_combo_mark_horizonal_white_bkgd.png" alt="Space Telescope Science Institute" width="83%" style="margin-left: auto;"/>
</a>

# {{ cookiecutter.project_name }}

[![build]({{ cookiecutter.repository_url }}/actions/workflows/build.yml/badge.svg)]({{ cookiecutter.repository_url }}/actions/workflows/build.yml)
[![tests]({{ cookiecutter.repository_url }}/actions/workflows/tests.yml/badge.svg)]({{ cookiecutter.repository_url }}/actions/workflows/tests.yml)
[![Powered by STScI](https://img.shields.io/badge/powered%20by-STScI-blue.svg?colorA=707170&colorB=3e8ddd&style=flat)](https://www.stsci.edu)
{%- if cookiecutter.publish_docs_to == 'readthedocs.io' %}
[![ReadTheDocs](https://readthedocs.org/projects/{{ cookiecutter.package_name }}/badge/?version=latest)](https://{{ cookiecutter.package_name }}.readthedocs.io/en/latest/?badge=latest)
{%- elif cookiecutter.publish_docs_to == 'github.io' %}
[![GitHub Pages]({{ cookiecutter.repository_url }}/actions/workflows/pages-build-deployment/badge.svg)](https://spacetelescope.github.io/{{ cookiecutter.package_name }})
{%- endif %}

{{ cookiecutter.project_description }}

## Reporting Bugs / Requesting a New Feature

If you encounter a bug or would like a new feature, open an issue:
{{ cookiecutter.repository_url }}/issues

## Suggesting Code Changes / Contributions

This package is open source at {{ cookiecutter.repository_url }}.
New contributions and contributors are very welcome!
All contributors should abide by the [Space Telescope Code of Conduct](./CODE_OF_CONDUCT.md).

> [!TIP]
> If you are new to GitHub, `git`, or version-control systems in general,
> refer to the [GitHub tutorial](https://docs.github.com/en/get-started/git-basics/set-up-git)
> and / or the [`git` reference manual](https://git-scm.com/docs),
> or reach out to a package maintainer for help.

To suggest a specific code change, or to contribute new code:

1. Fork this repository: {{ cookiecutter.repository_url }}/fork
2. Clone your fork to your local machine.
3. Install `pre-commit` with `pip install pre-commit`, and then set up commit hooks with `pre-commit install`
4. Install the package with `pip install -e .`, ideally to a fresh virtualenv or Conda environment.
5. Switch to a new branch (`git switch -b my_cool_feature`) and use your editor of choice to make changes to the codebase.
6. Commit your changes (`git commit`) and push your branch to the remote (`git push`).
7. Open a new pull request: {{ cookiecutter.repository_url }}/pulls
8. Complete any required items in the pull request description.

> [!NOTE]
> Code style generally conforms to [PEP8](https://peps.python.org/pep-0008/),
> enforced using [`ruff`](https://docs.astral.sh/ruff/).
> `ruff` will automatically pick up the appropriate configuration and perform only the checks that are turned on for our repository.

> [!NOTE]
> Docstrings conform to the [Numpy style guide](https://numpydoc.readthedocs.io/en/latest/format.html), enforced with [`numpydoc-validation`](https://numpydoc.readthedocs.io/en/latest/validation.html).
