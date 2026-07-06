# Build-and-boot smoke tier

The offline unit suite proves the generated artifacts render correctly; this tier
proves the generated image actually builds and boots. It runs in CI (the `build`
job in `.github/workflows/test.yml`) and needs Docker but no Cloudron account.

## What it does

For each Dockerfile shape it builds an image and boots it under the constraints
Cloudron imposes - a readonly root filesystem with writable `/run` and `/app/data`
only, and the `CLOUDRON_*` addon environment - then polls the health check for a
2xx and asserts supervisor brought up every long-running program the shape
renders. Postgres and Redis run as local containers standing in for the addons.

A 2xx proves the image builds, the settings import cleanly with every addon
variable present, collectstatic and migrate run (so Postgres is genuinely
reached), and the app serves HTTP. Redis, mail, and OIDC are validated only at
settings import, not by a live round-trip - the static health view does not
touch them.

Because supervisor keeps gunicorn serving even if the Celery worker or beat
crash-loop, a 2xx alone would not catch a dead worker. After the health check the
harness runs `supervisorctl status` and requires the expected programs to be
RUNNING: `gunicorn` and `nginx` for the retrofit cell, plus `celery-worker` and
`celery-beat` for the greenfield cell.

The retrofit cell hand-assembles a minimal requirements.txt project and renders
the artifact set through the packaging core, so it validates the generated
Dockerfile, settings, and boot - not the deploy-time dependency resolution
(`_add_requirements`), which the offline suite covers. Its pins are kept at or
above the deployer's `_REQUIREMENT_FLOORS`. The greenfield cell builds from the
real project template, so its dependency set is exactly what ships.

## Run it locally

Requires Docker.

    # retrofit (requirements.txt -> uv) shape
    CTX="$(mktemp -d)" && python tests/build_tests/assemble_retrofit_sample.py "$CTX"
    bash tests/build_tests/boot_smoke.sh "$CTX" retrofit-lean

    # greenfield (pyproject -> uv) shape
    OUT="$(mktemp -d)" && dsd-cloudron new "Smoke App" --celery --sso --output-dir "$OUT"
    CTX="$(find "$OUT" -mindepth 1 -maxdepth 1 -type d | head -n1)"
    bash tests/build_tests/boot_smoke.sh "$CTX" greenfield-full

A green run ends with `All expected supervisor programs are RUNNING`. A failure
dumps the container logs.
