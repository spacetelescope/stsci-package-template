=============================
Cookiecutter Template Options
=============================

You can use `Cookiecutter <https://github.com/cookiecutter/cookiecutter>`_ to build this template::

	cookiecutter https://github.com/spacetelescope/stsci-package-template.git

To keep your package updated with changes to this template,
use `Cruft <https://cruft.github.io/cruft>`_ instead of Cookiecutter::

	cruft create https://github.com/spacetelescope/stsci-package-template.git

General Options
---------------

These options are applicable to all package templates.

``project_name`` (**required**)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Name of your project.

``package_name``
^^^^^^^^^^^^^^^^

Importable name of your package.

By default, this is your project name in lowercase with spaces and hyphens replaced by underscores.
For instance, ``My Cool-Package`` would be ``my_cool_package``.

``repository_url``
^^^^^^^^^^^^^^^^^^

The URL of your package repository.

By default, this will be ``https://github.com/spacetelescope/<package_name>``,
using ``package_name`` from above.

``git_username`` (**required**)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Your username at the URL defined above.

``project_description`` (**required**)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A description of your project, in a sentence or two.

``manage_changelog_with_towncrier``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Whether to use `Towncrier <https://github.com/twisted/towncrier>`_
to manage changelog entries.
Towncrier reads RST files from the ``changes/`` directory and
combines them into a new changelog entry for a new version in ``CHANGES.rst``.

``publish_docs_to``
^^^^^^^^^^^^^^^^^^^

Whether to set up documentation publishing to either
`ReadTheDocs <https://app.readthedocs.org>`_ (``readthedocs.io``)
or `GitHub Pages <https://docs.github.com/en/pages>`_ (``github.io``).
Defaults to ``none``.

Python-specific options
-----------------------

These options are only applicable for generating a Python package.

``task_runner``
^^^^^^^^^^^^^^^

Whether to set up a task runner, either `Tox <https://tox.wiki>`_ or `Nox <https://nox.thea.codes>`_.
Defaults to ``none``.

``python_version``
^^^^^^^^^^^^^^^^^^

Version specification of Python to use for your package
(``requires-python`` in ``pyproject.toml``).
Defaults to ``>=3.12`` for "Python 3.12 and above".

``python_c_extensions``
^^^^^^^^^^^^^^^^^^^^^^^

Whether to build C extensions.

.. caution::
	This option is currently only automatically available with the ``setuptools`` build backend (see below);
	You will need to manually enter extension configuration in ``setup.py``.
	To build C extensions with `hatchling` you will need to manually set up the Hatch project manager with the `hatch-cython` plugin.

``python_build_backend``
^^^^^^^^^^^^^^^^^^^^^^^^

`Build backend to use <https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#declaring-the-build-backend>`_
when building the package.
This can either be ``setuptools`` or ``hatchling``.

``crds_observatory``
^^^^^^^^^^^^^^^^^^^^

Whether to set up CRDS caching in the test workflow;
either ``none``, ``roman``, ``jwst``, or ``hst``.
Default to ``none``.
