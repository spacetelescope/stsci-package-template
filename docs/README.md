# Writing and maintaining documentation

Documentation for `stsci_package_template` is written in [Sphinx reStructuredText (`.rst`)](https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html)
in this `docs/` directory, and is hosted online at https://spacetelescope.github.io/stsci-package-template

### Building documentation locally

To build the docs locally (assuming you have [set up your environment as described in `CONTRIBUTING.md`](../CONTRIBUTING.md#creating-a-development-environment)):

```shell
cd docs/
pip install ..[docs]
make clean
make html
```

The docs will build to `docs/_build/html/`.
Open `docs/_build/html/index.html` to view the pages in your browser.
