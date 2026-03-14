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

GitHub Actions is restricted to test execution only. Publishing is a manual step.

Build and upload artifacts locally:

```bash
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

## 4. Post-release

- Create/verify release notes in GitHub.
- Start next development cycle by opening a new `Unreleased` section in `CHANGELOG.md`.
