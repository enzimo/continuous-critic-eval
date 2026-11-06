# Build and verify packages

The project builds a wheel for installation and a source distribution containing
application code, review guides, tests and synthetic fixtures.

## Build

From the repository root, using the development environment:

```bash
.venv/bin/python -m pip install build
.venv/bin/python -m build
```

The outputs appear in `dist/`. Package metadata declares `Apache-2.0`, and both
formats include [LICENSE](../LICENSE). `MANIFEST.in` includes the test helpers,
documentation and fixture files used by the development checks.

## Verify

Run the checks in [README.md](../README.md#development-checks). Inspect both
archives, install the wheel in an isolated environment, and check the health
route, dashboard and static assets. Extract the source distribution and run its
test suite to verify that its helpers and fixtures are available.

Docker images use the same package metadata. The build stage copies the README
and license with `pyproject.toml` before installing the application. Verify image
execution and storage behavior in the target environment using
[the deployment guide](../deploy/swarm.md).
