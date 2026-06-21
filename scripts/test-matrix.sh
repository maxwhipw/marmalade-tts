#!/usr/bin/env bash
# Cross-distro test matrix — runs the non-engine suite in fresh distro containers.
#
# Runner-independent: needs only Docker locally (no CI runner). Mirrors
# .github/workflows/ci.yml so you can reproduce CI on your box. Proves the
# package + its core deps (pyyaml, num2words, uv) install cleanly and the fast
# suite passes on each distro. Skips `smoke` tests (they need installed engine
# binaries — kokoro/piper/coqui/… — which aren't available in a clean container).
#
# Usage:
#   scripts/test-matrix.sh                 # default image set
#   scripts/test-matrix.sh debian:12       # one or more specific images
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
MARKERS="${MTTS_MARKERS:-not smoke}"
IMAGES=("$@")
if [ ${#IMAGES[@]} -eq 0 ]; then
    IMAGES=(debian:12 ubuntu:22.04 ubuntu:24.04 fedora:40)
fi

apt_setup='apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv >/dev/null'
dnf_setup='dnf install -y -q python3 python3-pip >/dev/null'

run_one() {
    local image="$1" setup
    case "$image" in
        *debian*|*ubuntu*) setup="$apt_setup" ;;
        *fedora*)          setup="$dnf_setup" ;;
        *) echo "‼ no setup recipe for $image" >&2; return 2 ;;
    esac
    echo "═══ $image ═══"
    # Install into a per-container venv (not system Python): uniform across
    # distros, sidesteps PEP 668 'externally-managed' on Ubuntu 24.04 / Debian 12
    # and the 'cannot uninstall debian pip (no RECORD)' error, and lets us upgrade
    # pip freely (old distro pips misparse PEP 621 metadata and drop extras).
    # Build/install straight from the read-only mount (pip builds in a temp dir,
    # so it sees the whole repo incl. the force-included daemon scripts); run
    # pytest from a writable cwd with the cache redirected off the ro mount.
    docker run --rm -v "$REPO":/src:ro "$image" bash -c "
        set -e
        $setup
        python3 -m venv /venv
        /venv/bin/pip install -q --upgrade pip
        /venv/bin/pip install -q '/src[dev]'
        cd /tmp
        /venv/bin/python -m pytest /src/tests -m '$MARKERS' -o cache_dir=/tmp/ptcache
    "
}

fail=0
for img in "${IMAGES[@]}"; do
    if run_one "$img"; then echo "✓ $img PASSED"; else echo "✗ $img FAILED"; fail=1; fi
    echo
done
exit $fail
