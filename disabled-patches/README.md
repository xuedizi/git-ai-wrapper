# disabled patches

Files in this directory are retained for investigation and recovery only.
`scripts/build-git-ai.sh` and `scripts/test-patched-git-ai.sh` do not scan this
directory, so these patches are not applied to or embedded in sidecar binaries.
They remain available in repository source archives.

There are currently no disabled patches.

Re-enable a patch only through a reviewed wrapper change: move the patch to
`patches/`, restore its focused regression in `scripts/test-patched-git-ai.sh`,
update the exact active-set assertions and documentation, run the full wrapper
verification, and publish a new wrapper version. Do not enable it through a
runtime flag or by mutating an existing release.
