# Writing and maintaining documentation

Documentation for `{{ cookiecutter.package_name }}` is written in [Sphinx reStructuredText (`.rst`)](https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html)
in this `docs/` directory, and is hosted online at {% if cookiecutter.publish_docs_to == 'readthedocs.io' -%}https://{{ cookiecutter.package_name }}.readthedocs.io{%- elif cookiecutter.publish_docs_to == 'github.io' -%}https://spacetelescope.github.io/{{ cookiecutter.package_name }}{%- endif %}

### Building documentation locally
{% if cookiecutter.publish_docs_to == 'readthedocs.io' %}
ReadTheDocs will automatically build documentation for your branch when you push a commit to a pull request on this GitHub repository, and host a temporary build with a visual diff.
However, it is also good practice to build the docs locally if you are editing them, to reduce frustration from small errors.
{%- endif %}

To build the docs locally (assuming you have [set up your environment as described in `CONTRIBUTING.md`](../CONTRIBUTING.md#creating-a-development-environment)):

```shell
cd docs/
pip install ..[docs]
make clean
make html
```

The docs will build to `docs/_build/html/`.
Open `docs/_build/html/index.html` to view the pages in your browser.
