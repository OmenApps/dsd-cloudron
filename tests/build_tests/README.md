# Build-and-boot smoke tier

The offline unit suite proves the generated artifacts render correctly; this tier
proves the generated image actually builds and boots. It runs in CI (the `build`
job in `.github/workflows/test.yml`) and needs Docker but no Cloudron account.

## What it does

For each Dockerfile shape it builds an image and boots it under the constraints
Cloudron imposes - a readonly root filesystem with writable `/run` and `/app/data`
only, and the `CLOUDRON_*` addon environment - then polls the health check for a
2xx. Postgres and Redis run as local containers standing in for the addons.

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

A green run ends with `Health check passed`. A failure dumps the container logs.
