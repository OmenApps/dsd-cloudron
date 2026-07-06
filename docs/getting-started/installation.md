# Installation

`dsd-cloudron` is a [django-simple-deploy](https://django-simple-deploy.readthedocs.io)
plugin. Installing it pulls in django-simple-deploy itself, so a single
install gives you both the core deploy command and the Cloudron-specific
configuration it needs.

## Install the package

```bash
pip install dsd-cloudron
```

If you manage your project with [uv](https://docs.astral.sh/uv/), add it to
your environment instead:

```bash
uv add dsd-cloudron
```

Either command pulls in django-simple-deploy along with the plugin.

## Install the Cloudron CLI

Deploying to a Cloudron server also requires the `cloudron` command line
tool, which `dsd-cloudron` shells out to for builds and installs:

```bash
npm install -g cloudron
```

## Authenticate with your Cloudron server

```bash
cloudron login my.example.com
```

Log in once before running a deploy. `dsd-cloudron` reuses that logged-in
session rather than taking an API token on the command line.

## Requirements

`dsd-cloudron` supports Python 3.11+ and Django 4.2+.

With the package installed and `cloudron` authenticated, scaffold a new
project (see {doc}`quickstart`) or configure an existing one for
deployment.
