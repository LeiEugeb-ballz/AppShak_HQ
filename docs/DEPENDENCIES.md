# Dependency Guidance

This document is the canonical dependency **documentation** for the active
repository. It records the installation instructions currently present in the
project; it does not introduce a package manifest or alter runtime behaviour.

## Python runtime

`ENVIRONMENT_SETUP.md` specifies Python 3.10 or newer and the following
installation command:

```bash
python -m pip install fastapi "uvicorn[standard]" websockets aiofiles
```

The active source imports FastAPI, Uvicorn, WebSockets-related functionality,
and Pydantic through FastAPI-facing modules. Core kernel, substrate,
governance, projection, integrity, stability, inspection, and most test code
also use the Python standard library.

There is currently no active root `requirements.txt`, `pyproject.toml`,
`setup.py`, or `setup.cfg`. The only tracked `requirements.txt` is located in
`stashed_instances_2026-02-19/appshak_live/` and belongs to that archived
implementation.

## Frontend runtime

The observability UI is independently defined by:

- [`appshak-ui/package.json`](../appshak-ui/package.json)
- [`appshak-ui/package-lock.json`](../appshak-ui/package-lock.json)

It requires Node.js 18 or newer according to
[ENVIRONMENT_SETUP.md](../ENVIRONMENT_SETUP.md). Install and run it with:

```bash
cd appshak-ui
npm install
npm run dev
```

## Verification tooling

- Python tests use the standard-library `unittest` runner.
- `pytest.ini` also configures pytest discovery for `tests/`.
- The frontend package defines `dev`, `build`, `lint`, and `preview` scripts.

## Canonical setup path

Use [ENVIRONMENT_SETUP.md](../ENVIRONMENT_SETUP.md) for the complete setup and
smoke-test sequence, then return to [README.md](../README.md) for runtime and
observation commands.

## Dependency-manifest observation

A versioned active Python dependency manifest would be the normal future
canonical dependency definition for reproducible installation. Creating one is
outside this documentation-only mission; this document makes the current
absence and existing installation instructions explicit.
