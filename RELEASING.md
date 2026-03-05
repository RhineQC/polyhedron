# Releasing Polyhedron

This document describes the release checklist for public versions.

## 1. Prepare release PR

- Ensure CI is green for base and optional test profiles.
- Update `CHANGELOG.md` (move items from `Unreleased` into target version section).
- Confirm version bump in `pyproject.toml`.

## 2. Tag release

After merging release changes:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

## 3. Publish artifacts

The GitHub workflow `.github/workflows/release.yml` builds source/wheel artifacts
and publishes on tag pushes.

## 4. Post-release

- Create/verify release notes in GitHub.
- Start next development cycle by opening a new `Unreleased` section in `CHANGELOG.md`.
