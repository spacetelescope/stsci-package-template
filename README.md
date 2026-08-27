<a href="https://stsci.edu">
  <img src="docs/_static/stsci_pri_combo_mark_horizonal_white_bkgd.png" alt="Space Telescope Science Institute" width="83%" style="margin-left: auto;"/>
</a>

# STScI Package Template

This [Cookiecutter template](https://github.com/cookiecutter/cookiecutter)
defines best practices and boilerplate for STScI packages.

To generate files for a package, install [Cruft](https://cruft.github.io/cruft),
run the following, and answer the prompts:

```shell
cruft create https://github.com/spacetelescope/stsci-package-template.git --directory python-package
```

Then, `cd` to the newly-generated package directory and initialize version control:

```shell
cd my_package/
git init
git commit -am "cookiecutter'd files"
```

This template [includes a GitHub Actions workflow](/templates/.github/workflows/update.yml) that
[runs Cruft to automatically check for updates](https://cruft.github.io/cruft/#updating-a-project).
You can also do this manually with `cruft update`.

## Acknowledgements

Adapted from [Cookiecutter PyPackage](https://github.com/audreyfeldroy/cookiecutter-pypackage)
