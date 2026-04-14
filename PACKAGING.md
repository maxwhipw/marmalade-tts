# PACKAGING.md — Maintainer Guide

How to build and publish marmalade-tts packages.

---

## Prerequisites

```sh
# Python build tools
pip install build twine

# fpm (for deb/rpm)
gem install fpm

# Optional: age (for encrypted Forgejo release uploads via CLI)
```

---

## PyPI

### Build

```sh
python3 -m build
# Produces: dist/marmalade_tts-0.4.0.tar.gz
#           dist/marmalade_tts-0.4.0-py3-none-any.whl
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
# Produces: marmalade-tts_0.4.0_amd64.deb
```

### Test locally

```sh
sudo dpkg -i marmalade-tts_0.4.0_amd64.deb
marmalade-tts --version
sudo dpkg -r marmalade-tts
```

---

## rpm (Fedora / RHEL / openSUSE)

### Build

```sh
make rpm
# Produces: marmalade-tts-0.4.0-1.x86_64.rpm
```

### Test locally

```sh
sudo rpm -i marmalade-tts-0.4.0-1.x86_64.rpm
marmalade-tts --version
sudo rpm -e marmalade-tts
```

---

## Forgejo Release

1. Tag the release:

   ```sh
   git tag -a v0.4.0 -m "Release 0.4.0"
   git push origin v0.4.0
   ```

2. Build all packages:

   ```sh
   make deb rpm pypi
   ```

3. Create the release on Forgejo and attach artifacts:

   Go to: `http://george:3000/marmalade/marmalade-tts-cli/releases/new`

   Attach:
   - `marmalade-tts_0.4.0_amd64.deb`
   - `marmalade-tts-0.4.0-1.x86_64.rpm`
   - `dist/marmalade_tts-0.4.0.tar.gz`
   - `dist/marmalade_tts-0.4.0-py3-none-any.whl`

   Or via Forgejo CLI / API:
   ```sh
   # Using the Forgejo API (requires token)
   TOKEN="your-token"
   REPO="marmalade/marmalade-tts-cli"
   TAG="v0.4.0"
   BASE="http://george:3000"
   
   # Create release
   curl -s -X POST "${BASE}/api/v1/repos/${REPO}/releases" \
     -H "Authorization: token ${TOKEN}" \
     -H "Content-Type: application/json" \
     -d "{\"tag_name\":\"${TAG}\",\"name\":\"${TAG}\",\"body\":\"Release ${TAG}\"}"
   
   # Upload assets (get release_id from above response)
   RELEASE_ID=1
   for f in marmalade-tts_0.4.0_amd64.deb marmalade-tts-0.4.0-1.x86_64.rpm; do
     curl -s -X POST "${BASE}/api/v1/repos/${REPO}/releases/${RELEASE_ID}/assets" \
       -H "Authorization: token ${TOKEN}" \
       -F "attachment=@${f}"
   done
   ```

---

## AUR (Arch Linux)

The PKGBUILD is at `packaging/aur/PKGBUILD`.

### Update for a new version

1. Update `pkgver` and `pkgrel` in `packaging/aur/PKGBUILD` and `packaging/aur/.SRCINFO`.

2. Update `sha256sums` once the tarball is published:

   ```sh
   # After the Forgejo release tarball is available:
   sha256sum marmalade-tts-0.4.0.tar.gz
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
   git commit -m "Update to 0.4.0"
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
