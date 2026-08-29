#!/usr/bin/env bash
# Generate git-ai-manifest.json for packaged git-ai sidecar archives.
set -euo pipefail

usage() {
	cat <<'EOF'
generate-manifest.sh --version <wrapper-version> --upstream <git-ai-version> --dir <artifact-dir> --out <manifest>

Scans git-ai-*.tar.gz files and writes sha256/size metadata used by TAC when
fetching git-ai sidecars.
EOF
}

VERSION=""
UPSTREAM=""
DIR=""
OUT=""
while [ $# -gt 0 ]; do
	case "$1" in
		--version) VERSION="$2"; shift 2 ;;
		--version=*) VERSION="${1#*=}"; shift ;;
		--upstream) UPSTREAM="$2"; shift 2 ;;
		--upstream=*) UPSTREAM="${1#*=}"; shift ;;
		--dir) DIR="$2"; shift 2 ;;
		--dir=*) DIR="${1#*=}"; shift ;;
		--out) OUT="$2"; shift 2 ;;
		--out=*) OUT="${1#*=}"; shift ;;
		-h|--help) usage; exit 0 ;;
		*) echo "generate-manifest.sh: unknown arg: $1" >&2; usage >&2; exit 2 ;;
	esac
done

[ -n "$VERSION" ] || { echo "generate-manifest.sh: --version required" >&2; exit 2; }
[ -n "$UPSTREAM" ] || { echo "generate-manifest.sh: --upstream required" >&2; exit 2; }
[ -n "$DIR" ] || { echo "generate-manifest.sh: --dir required" >&2; exit 2; }
[ -n "$OUT" ] || { echo "generate-manifest.sh: --out required" >&2; exit 2; }
[ -d "$DIR" ] || { echo "generate-manifest.sh: dir not found: $DIR" >&2; exit 1; }

sha256_cmd() {
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$1" | awk '{print $1}'
	else
		shasum -a 256 "$1" | awk '{print $1}'
	fi
}

tmp=$(mktemp -t git-ai-manifest.XXXXXX)
{
	printf '{\n'
	printf '  "version": "%s",\n' "$VERSION"
	printf '  "upstream_git_ai": "%s",\n' "$UPSTREAM"
	printf '  "artifacts": {\n'
	first=1
	found=0
	for f in "$DIR"/git-ai-*.tar.gz; do
		[ -f "$f" ] || continue
		found=1
		name=$(basename "$f")
		sha=$(sha256_cmd "$f")
		size=$(wc -c < "$f" | tr -d ' ')
		if [ "$first" -eq 1 ]; then
			first=0
		else
			printf ',\n'
		fi
		printf '    "%s": { "sha256": "%s", "size": %s }' "$name" "$sha" "$size"
	done
	printf '\n  }\n'
	printf '}\n'
} > "$tmp"

[ "$found" -eq 1 ] || { rm -f "$tmp"; echo "generate-manifest.sh: no git-ai-*.tar.gz files in $DIR" >&2; exit 1; }
mkdir -p "$(dirname "$OUT")"
mv "$tmp" "$OUT"
echo ">> wrote $OUT"
