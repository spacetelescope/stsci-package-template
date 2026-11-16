<a href="https://stsci.edu">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://github.com/spacetelescope/branding/blob/81b7021231e885bda9c022e6c082b3cf26009b3b/stsci_pri_combo_mark_horizonal_dark_bkgd.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://github.com/spacetelescope/branding/blob/81b7021231e885bda9c022e6c082b3cf26009b3b/stsci_pri_combo_mark_horizonal_light_bkgd.svg">
    <img src="https://github.com/spacetelescope/branding/blob/81b7021231e885bda9c022e6c082b3cf26009b3b/stsci_pri_combo_mark_horizonal_white_bkgd.svg" alt="Space Telescope Science Institute" width="83%" style="margin-left: auto;"/>
  </picture>
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
