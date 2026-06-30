# dsd-cloudron

A [django-simple-deploy](https://django-simple-deploy.readthedocs.io) plugin that
configures and deploys Django projects to [Cloudron](https://cloudron.io). One
install serves two audiences: retrofit an existing project with
`python manage.py deploy`, or scaffold a brand new one with `dsd-cloudron new`.
Either path renders the same Cloudron artifact set - manifest, Dockerfile,
start.sh, supervisor configs, nginx, settings glue - through a single shared
packaging core.

```{toctree}
:caption: Getting started
:maxdepth: 2

getting-started/installation
getting-started/quickstart
```

```{toctree}
:caption: Guides
:maxdepth: 2

guides/retrofit-existing-project
guides/scaffold-new-project
```
