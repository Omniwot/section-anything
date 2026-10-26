# Releasing

The library in `packages/section-anything` is published to PyPI by
[`.github/workflows/release.yml`](.github/workflows/release.yml) when a version tag is pushed.
It uses PyPI trusted publishing, so no API token is stored in the repository.

## Each release

1. Bump `version` in `packages/section-anything/pyproject.toml`, `__version__` in
   `packages/section-anything/src/section_anything/__init__.py` and `version` in `CITATION.cff`,
   and add the release to `CHANGELOG.md`.
2. Merge to `main`.
3. Tag that commit and push the tag:

   ```sh
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

The workflow checks that the tag matches the version, builds the sdist and wheel, runs
`twine check --strict` and publishes to PyPI.

## One-time setup

- On PyPI (Account settings, Publishing), add a pending publisher: project `section-anything`,
  owner `Omniwot`, repository `section-anything`, workflow `release.yml`, environment `pypi`.
- On GitHub (Settings, Environments), create the environment `pypi`.

## Integration packages

`langchain-section-anything` and `llama-index-readers-section-anything` are published by
[`.github/workflows/release-integrations.yml`](.github/workflows/release-integrations.yml), one
package per tag, with the same trusted publishing and the same `pypi` environment.

1. Bump `version` in the package's `pyproject.toml` and `__version__` in its `__init__.py`.
2. Merge to `main`, then tag that commit with the package name and version and push the tag:

   ```sh
   git tag langchain-section-anything-v0.1.0            # or llama-index-readers-section-anything-v0.1.0
   git push origin langchain-section-anything-v0.1.0
   ```

The workflow checks that the tag names one of the two packages and matches its version, builds
it, runs `twine check --strict` and publishes it. A library release that an integration needs
goes first (the integrations require `section-anything>=0.1.1,<0.2`).

One-time setup, on PyPI (Account settings, Publishing), one pending publisher per package:

| PyPI project | Owner | Repository | Workflow | Environment |
|---|---|---|---|---|
| `langchain-section-anything` | `Omniwot` | `section-anything` | `release-integrations.yml` | `pypi` |
| `llama-index-readers-section-anything` | `Omniwot` | `section-anything` | `release-integrations.yml` | `pypi` |
