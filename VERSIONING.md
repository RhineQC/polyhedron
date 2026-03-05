# Versioning Policy

Polyhedron uses Semantic Versioning (`MAJOR.MINOR.PATCH`).

## Version bump rules

- `PATCH`: bug fixes, doc fixes, internal refactors without public API change.
- `MINOR`: backward-compatible feature additions or new optional modules.
- `MAJOR`: breaking changes in public API, behavior, or supported compatibility.

## Pre-release tags

Use pre-release versions for release candidates when needed:

- `X.Y.Z-rc.1`
- `X.Y.Z-beta.1`

## Release branch and tags

- Default development happens on feature branches.
- Release commits are tagged as `vX.Y.Z`.
- Tag message should summarize highlights and point to `CHANGELOG.md`.

## Changelog requirement

Every merged PR that changes behavior must update `CHANGELOG.md` under `Unreleased`.
