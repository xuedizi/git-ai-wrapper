#!/usr/bin/env bash
# Apply every active downstream patch to the pinned upstream tag and run the
# regressions that must pass before any native release build starts.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
ROOT_DIR=$(dirname "$SCRIPT_DIR")
PATCH_DIR="$ROOT_DIR/patches"

command -v git >/dev/null || { echo "test-patched-git-ai.sh: git required" >&2; exit 1; }
command -v cargo >/dev/null || { echo "test-patched-git-ai.sh: cargo required" >&2; exit 1; }

GIT_AI_VERSION=$(cat "$PATCH_DIR/GIT_AI_VERSION")
[ -n "$GIT_AI_VERSION" ] || {
	echo "test-patched-git-ai.sh: $PATCH_DIR/GIT_AI_VERSION is empty" >&2
	exit 1
}

shopt -s nullglob
patch_candidates=("$PATCH_DIR"/*.patch)
active_patch_names=()
for patch_file in "${patch_candidates[@]}"; do
	[ -f "$patch_file" ] && [ ! -L "$patch_file" ] || {
		echo "test-patched-git-ai.sh: active patch must be a real regular file: $patch_file" >&2
		exit 1
	}
	active_patch_names+=("$(basename "$patch_file")")
done
if [ "${#active_patch_names[@]}" -gt 0 ]; then
	sorted_patch_names=()
	while IFS= read -r patch_name; do
		sorted_patch_names+=("$patch_name")
	done < <(printf '%s\n' "${active_patch_names[@]}" | LC_ALL=C sort)
	active_patch_names=("${sorted_patch_names[@]}")
fi

expected_patch_names=(
	"codebuddy-preset.patch"
	"enterprise-metrics.patch"
	"install-hooks-target.patch"
	"managed-update.patch"
)
actual_patch_names=$(printf '%s\n' "${active_patch_names[@]}")
expected_patch_names_text=$(printf '%s\n' "${expected_patch_names[@]}")
[ "$actual_patch_names" = "$expected_patch_names_text" ] || {
	echo "test-patched-git-ai.sh: unexpected active patch list; expected $expected_patch_names_text; got: $actual_patch_names" >&2
	exit 1
}

active_patch_files=()
for patch_name in "${active_patch_names[@]}"; do
	active_patch_files+=("$PATCH_DIR/$patch_name")
done

WORK=$(mktemp -d -t git-ai-patch-tests.XXXXXX)
trap 'rm -rf "$WORK"' EXIT
GIT_AI_GIT_URL="${TAC_GIT_AI_GIT_URL:-https://github.com/git-ai-project/git-ai.git}"

git -c http.version=HTTP/1.1 clone --depth 1 --branch "$GIT_AI_VERSION" \
	--single-branch "$GIT_AI_GIT_URL" "$WORK/src" >/dev/null

for patch_file in "${active_patch_files[@]}"; do
	echo ">> applying $(basename "$patch_file")"
	(cd "$WORK/src" && git apply "$patch_file")
done

# Existing TestRepo fixtures intentionally reuse one executable across many homes.
# Exercise standalone behavior for those fixtures; managed lifecycle tests copy
# a separate installation per home and enable the managed build explicitly.
export TCLI_MANAGED_GIT_AI=0
export CARGO_HOME="${CARGO_HOME:-$HOME/.cargo}"
# Local HTTP/TLS fixtures must not be routed through an external proxy.
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-${no_proxy:-}}"
echo ">> running patched upstream tests (cargo test)"
(cd "$WORK/src" && cargo test --locked --lib)
(cd "$WORK/src" && cargo test --locked --test integration enterprise_metrics)

(cd "$WORK/src" && cargo test --locked --test integration test_edge_extension_recovery_metric_copies_source_session_tool_and_model)

(cd "$WORK/src" && cargo test --locked --test integration install_hooks_target)

(cd "$WORK/src" && cargo test --locked --test integration codebuddy_cwd)

(cd "$WORK/src" && TCLI_MANAGED_GIT_AI=1 cargo test --locked --test integration managed_update -- --test-threads 1)
