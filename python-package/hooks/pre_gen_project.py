import re
import sys
import warnings

MODULE_REGEX = r"^([_a-zA-Z]+[_a-zA-Z\d]+)$"

PACKAGE_NAME = "{{ cookiecutter.package_name }}"

PYTHON_BUILD_BACKEND = "{{ cookiecutter.python_build_backend }}"
PYTHON_C_EXTENSIONS = "{{ cookiecutter.python_c_extensions }}" == "True"

if not re.match(MODULE_REGEX, PACKAGE_NAME):
    print(
        f"WARNING: `{PACKAGE_NAME}` may not be importable as a module name in Python",
        file=sys.stderr,
    )

if PYTHON_C_EXTENSIONS:
    print(
        "Reminder: you will need to manually configure your C extensions"
        + "in `setup.py` (https://setuptools.pypa.io/en/latest/userguide/ext_modules.html)"
        if PYTHON_BUILD_BACKEND == "setuptools"
        else "using the `hatch-cython` Hatch plugin (https://github.com/joshua-auchincloss/hatch-cython)"
        if PYTHON_BUILD_BACKEND == "hatchling"
        else "",
        file=sys.stderr,
    )
