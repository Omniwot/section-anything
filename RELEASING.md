# Releasing

The library in `packages/section-anything` is published to PyPI by
[`.github/workflows/release.yml`](.github/workflows/release.yml) when a version tag is pushed.
It uses PyPI trusted publishing, so no API token is stored in the repository.

## Each release

1. Bump `version` in `packages/section-anything/pyproject.toml`, `__version__` in
   `packages/section-anything/src/section_anything/__init__.py` and `version` in `CITATION.cff`,
   and add the release to `CHANGELOG.md`.
   Check that the default models in `packages/section-anything/src/section_anything/config.py`
   (`quick_model`, `standard_model`, both `gpt-6-luna` since 0.1.3) are the ones the published
   scores and costs in the READMEs and `site/data/results.js` were measured on.
2. Merge to `main`.
3. Tag that commit and push the tag:

   ```sh
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

The workflow checks that the tag matches the version, builds the sdist and wheel, runs
`twine check --strict` and publishes to PyPI.

## One-time setup

Done (the library is on PyPI); kept for reference.

- On PyPI (Account settings, Publishing), add a pending publisher: project `section-anything`,
  owner `Omniwot`, repository `section-anything`, workflow `release.yml`, environment `pypi`.
- On GitHub (Settings, Environments), create the environment `pypi`.

## Integration packages

`langchain-section-anything`, `llama-index-readers-section-anything`, `lightrag-section-anything`
and `section-anything-mcp` (the MCP server wrapper, see below) are published by
[`.github/workflows/release-integrations.yml`](.github/workflows/release-integrations.yml), one
package per tag, with the same trusted publishing and the same `pypi` environment.

1. Bump `version` in the package's `pyproject.toml` and `__version__` in its `__init__.py`.
2. Merge to `main`, then tag that commit with the package name and version and push the tag:

   ```sh
   git tag langchain-section-anything-v0.1.0  # or llama-index-readers-section-anything-v0.1.0, lightrag-section-anything-v0.1.0
   git push origin langchain-section-anything-v0.1.0
   ```

The workflow checks that the tag names one of the four packages and matches its version, builds
it, runs `twine check --strict` and publishes it. A library release that an integration needs
goes first (the integrations require `section-anything>=0.1.1,<0.2`).

One-time setup, on PyPI (Account settings, Publishing), one pending publisher per package (done:
all three were published in October 2026; kept for reference):

| PyPI project | Owner | Repository | Workflow | Environment |
|---|---|---|---|---|
| `langchain-section-anything` | `Omniwot` | `section-anything` | `release-integrations.yml` | `pypi` |
| `llama-index-readers-section-anything` | `Omniwot` | `section-anything` | `release-integrations.yml` | `pypi` |
| `lightrag-section-anything` | `Omniwot` | `section-anything` | `release-integrations.yml` | `pypi` |
| `section-anything-mcp` | `Omniwot` | `section-anything` | `release-integrations.yml` | `pypi` |

## MCP Registry

The MCP server is listed in the official MCP Registry as `io.github.Omniwot/section-anything`,
from [`server.json`](server.json). Registry clients start it with `uvx section-anything-mcp`,
which is why `packages/section-anything-mcp` exists: it depends on `section-anything[mcp]` and
provides the same `section-anything-mcp` command. The registry checks ownership from the
`mcp-name:` comment in that package's PyPI README.

1. Publish `section-anything-mcp` to PyPI first (tag `section-anything-mcp-vX.Y.Z`; one-time:
   its pending publisher, table above).
2. Set `version` in `server.json` (top level and the package entry) to that version.
3. Publish, signed in to GitHub as `Omniwot`
   ([`mcp-publisher`](https://github.com/modelcontextprotocol/registry/releases)):

   ```sh
   mcp-publisher login github
   mcp-publisher publish
   ```

The registry is in preview and may reset its data; publish again if the listing disappears.
