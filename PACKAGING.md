# PACKAGING.md — Maintainer Guide

How to build and publish marmalade-tts packages.

---

## Prerequisites

```sh
# Python build tools
pip install build twine

# fpm (for deb/rpm)
gem install fpm

# Optional: age (for encrypted GitHub release uploads via CLI)
```

---

## PyPI

### Build

```sh
python3 -m build
# Produces: dist/marmalade_tts-0.4.3.tar.gz
#           dist/marmalade_tts-0.4.3-py3-none-any.whl
```

### Upload

```sh
python3 -m twine upload dist/*
```

Or to test first on TestPyPI:

```sh
python3 -m twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ marmalade-tts
```

---

## deb (Debian / Ubuntu)

### Build

```sh
make deb
# Produces: marmalade-tts_0.4.3_amd64.deb
```

### Test locally

```sh
sudo dpkg -i marmalade-tts_0.4.3_amd64.deb
marmalade-tts --version
sudo dpkg -r marmalade-tts
```

---

## rpm (Fedora / RHEL / openSUSE)

### Build

```sh
make rpm
# Produces: marmalade-tts-0.4.3-1.x86_64.rpm
```

### Test locally

```sh
sudo rpm -i marmalade-tts-0.4.3-1.x86_64.rpm
marmalade-tts --version
sudo rpm -e marmalade-tts
```

---

## Release pipeline (PyPI + GitHub)

PyPI publishing and GitHub release-asset upload are automated by
`.github/workflows/publish.yml`, which runs on every `v*` tag push.

### One-time setup

These need to be done once, before the first automated release.

**1. PyPI Trusted Publisher**

Go to <https://pypi.org/manage/account/publishing/>, "Add a new pending
publisher", and fill in:

| Field                  | Value                |
|------------------------|----------------------|
| PyPI project name      | `marmalade-tts`      |
| Owner                  | `maxwhipw`           |
| Repository name        | `marmalade-tts`      |
| Workflow filename      | `publish.yml`        |
| Environment name       | `pypi`               |

PyPI authenticates the workflow via OIDC — no API tokens to manage.
Sigstore attestations are uploaded alongside each release.

**2. GitHub Environment**

In the GitHub repo, go to Settings → Environments → New environment →
name it `pypi`. The environment can optionally have:
- Required reviewers (manual approval before publish)
- Deployment branch rules restricted to `refs/tags/v*`

The workflow uses this environment so the PyPI Trusted Publisher
config matches.

### Cutting a release

```sh
# 1. Bump version
#    - marmalade_tts/__init__.py
#    - pyproject.toml
#    - packaging/aur/PKGBUILD + .SRCINFO
#    - README.md (deb/rpm filenames)
#    - docker/README.md (health response example)
#    - PACKAGING.md (build-artifact examples)
#    - CHANGELOG.md (promote [Unreleased] section)

# 2. Commit, then tag + push
git commit -am "Release X.Y.Z"
git tag -a vX.Y.Z -m "Release X.Y.Z"
git push github main
git push github vX.Y.Z
```

The `publish.yml` workflow then:

1. Builds the sdist + wheel via `python -m build`.
2. Verifies `marmalade_tts.__version__` matches the tag (fails otherwise).
3. Smoke-tests the wheel in a fresh venv.
4. Publishes to PyPI with Sigstore attestations (OIDC, no token).
5. Creates the GitHub release and attaches the wheel + sdist as assets.

You can watch progress at the repo's "Actions" tab.

### Local build (optional, for testing)

The same `.deb` and `.rpm` builds run unattended in the workflow, but
you can produce them locally for testing. Requires `fpm` (Ruby) and
`rpmbuild`:

```sh
sudo apt install ruby ruby-dev rpm
sudo gem install --no-document fpm
make deb rpm
```

---

## AUR (Arch Linux)

The PKGBUILD is at `packaging/aur/PKGBUILD`.

### Update for a new version

1. Update `pkgver` and `pkgrel` in `packaging/aur/PKGBUILD` and `packaging/aur/.SRCINFO`.

2. Update `sha256sums` once the tarball is published:

   ```sh
   # After the GitHub release tarball is available:
   VERSION=$(python3 -c "from marmalade_tts import __version__; print(__version__)")
   curl -L -o /tmp/marmalade-tts-${VERSION}.tar.gz \
     https://github.com/maxwhipw/marmalade-tts/archive/refs/tags/v${VERSION}.tar.gz
   sha256sum /tmp/marmalade-tts-${VERSION}.tar.gz
   # Replace 'SKIP' in PKGBUILD and .SRCINFO with the actual hash
   ```

3. Regenerate `.SRCINFO` (requires an Arch system with `makepkg`):

   ```sh
   cd packaging/aur
   makepkg --printsrcinfo > .SRCINFO
   ```

4. Push to the AUR:

   ```sh
   # Clone your AUR package repo (first time)
   git clone ssh://aur@aur.archlinux.org/marmalade-tts.git /tmp/aur-marmalade-tts
   
   # Copy updated files
   cp packaging/aur/PKGBUILD packaging/aur/.SRCINFO /tmp/aur-marmalade-tts/
   
   # Commit and push
   cd /tmp/aur-marmalade-tts
   git add PKGBUILD .SRCINFO
   git commit -m "Update to 0.4.3"
   git push
   ```

---

## Version Bump Checklist

When releasing a new version, update in all of these places:

- [ ] `marmalade_tts/__init__.py` — `__version__`
- [ ] `pyproject.toml` — `version`
- [ ] `packaging/aur/PKGBUILD` — `pkgver`
- [ ] `packaging/aur/.SRCINFO` — `pkgver`
- [ ] Git tag — `v<version>`

Run `make test` before tagging.
