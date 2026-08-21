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
