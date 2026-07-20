#!/bin/sh
set -eu

if ! command -v git-lfs >/dev/null 2>&1; then
    printf '%s\n' "Git LFS is required to push this repository's binary assets." >&2
    exit 2
fi

remote_name="${PRE_COMMIT_REMOTE_NAME:-origin}"
to_ref="${PRE_COMMIT_TO_REF:-HEAD}"

# A zero destination ref represents a branch or tag deletion and has no new
# LFS objects to upload.
case "$to_ref" in
    0000000000000000000000000000000000000000) exit 0 ;;
esac

git lfs push "$remote_name" "$to_ref"
