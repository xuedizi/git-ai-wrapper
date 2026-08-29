#!/usr/bin/env bash
# build-git-ai.sh — clone upstream git-ai-project/git-ai at the pinned version,
# apply patches/*.patch, build a standalone git-ai executable with cargo,
# copy it to --out.
#
# Default upstream: https://github.com/git-ai-project/git-ai (public).
# Override with TAC_GIT_AI_GIT_URL when building behind a network
# that can't reach github.com (e.g., an internal CI runner pointed at an
# internal mirror).
#
# The produced executable ships inside every tcli-<os>-<arch>.tar.gz so end
# users get CodeBuddy attribution support without installing Rust locally.
#
# Usage:
#   scripts/build-git-ai.sh --out <dir>   # build, copy executable to <dir>
#   scripts/build-git-ai.sh --rebase      # apply patches to a fresh upstream
#                                         # checkout, drop into a shell so the
#                                         # operator can resolve conflicts,
#                                         # write the rebased patch back to
#                                         # patches/codebuddy-preset.patch
#   scripts/build-git-ai.sh --help        # this text

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
ROOT_DIR=$(dirname "$SCRIPT_DIR")
PATCH_DIR="$ROOT_DIR/patches"

usage() {
	cat <<'EOF'
build-git-ai.sh — clone upstream git-ai + apply patches + build executable.

Used by `make release` at release time. The produced executable ships
inside every tcli-<os>-<arch>.tar.gz so end users get CodeBuddy attribution
support without client-side Rust installation.

Usage:
  build-git-ai.sh --out <dir>       build, copy executable to <dir>
  build-git-ai.sh --rebase          apply patches to a fresh upstream
                                    checkout, drop into a shell so the
                                    operator can resolve conflicts, write
                                    the rebased patch back to disk
  build-git-ai.sh --help            this text
EOF
}

OUT=""
MODE=build
while [ $# -gt 0 ]; do
	case "$1" in
		--out)     OUT="$2"; shift 2 ;;
		--out=*)   OUT="${1#*=}"; shift ;;
		--rebase)  MODE=rebase; shift ;;
		-h|--help) usage; exit 0 ;;
		*)         echo "build-git-ai.sh: unknown arg: $1" >&2; usage >&2; exit 2 ;;
	esac
done

command -v cargo >/dev/null || { echo "build-git-ai.sh: cargo required on release builder (install: https://rustup.rs)" >&2; exit 1; }
command -v git >/dev/null  || { echo "build-git-ai.sh: git required" >&2; exit 1; }

GIT_AI_VERSION=$(cat "$PATCH_DIR/GIT_AI_VERSION")
[ -n "$GIT_AI_VERSION" ] || { echo "build-git-ai.sh: $PATCH_DIR/GIT_AI_VERSION is empty" >&2; exit 1; }
echo ">> build-git-ai.sh: upstream pin = $GIT_AI_VERSION"

WORK=$(mktemp -d -t git-ai-build.XXXXXX)
trap 'rm -rf "$WORK"' EXIT

GIT_AI_GIT_URL="${TAC_GIT_AI_GIT_URL:-https://github.com/git-ai-project/git-ai.git}"
echo ">> cloning $GIT_AI_GIT_URL @ $GIT_AI_VERSION into $WORK/src"
git clone --depth 1 --branch "$GIT_AI_VERSION" \
	"$GIT_AI_GIT_URL" "$WORK/src" >/dev/null

echo ">> applying patches from $PATCH_DIR"
shopt -s nullglob
for p in "$PATCH_DIR"/*.patch; do
	echo "   - $(basename "$p")"
	(cd "$WORK/src" && git apply "$p")
done
BUILD_SHA=$(cd "$WORK/src" && git rev-parse --short HEAD)

if [ "$MODE" = rebase ]; then
	[ -t 0 ] || { echo "build-git-ai.sh: --rebase requires an interactive terminal (stdin is not a tty)" >&2; exit 1; }
	echo ">> --rebase: spawning shell in $WORK/src. Resolve conflicts, then:"
	echo "     git add -A && git diff --cached > $PATCH_DIR/codebuddy-preset.patch"
	echo "     exit"
	(cd "$WORK/src" && "$SHELL")
	echo ">> rebase shell exited; patch presumed updated on disk"
	exit 0
fi

[ -n "$OUT" ] || { echo "build-git-ai.sh: --out required for build mode" >&2; exit 2; }
mkdir -p "$OUT"
# Resolve to absolute path before the cd into $WORK/src.
OUT=$(cd "$OUT" && pwd -P)

echo ">> building standalone git-ai executable via cargo (release)"
(cd "$WORK/src" && cargo build --release)

exe="$WORK/src/target/release/git-ai"
if [ -f "$WORK/src/target/release/git-ai.exe" ]; then
	exe="$WORK/src/target/release/git-ai.exe"
fi
[ -f "$exe" ] || { echo "build-git-ai.sh: cargo produced no git-ai executable in $WORK/src/target/release" >&2; exit 1; }
chmod 0755 "$exe" 2>/dev/null || true
cp "$exe" "$OUT/$(basename "$exe")"
echo ">> executable in $OUT:"
ls -la "$OUT/$(basename "$exe")"
