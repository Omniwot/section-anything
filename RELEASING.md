# Releasing

The library in `packages/section-anything` is published to PyPI by
[`.github/workflows/release.yml`](.github/workflows/release.yml) when a version tag is pushed.
It uses PyPI trusted publishing, so no API token is stored in the repository.

## Each release

1. Bump `version` in `packages/section-anything/pyproject.toml` (and `version` in `CITATION.cff`).
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
