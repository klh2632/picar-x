#!/usr/bin/env bash
set -u

repo_dir="${1:-$(pwd)}"
message="${2:-auto-commit: local sync}"

if [ ! -d "$repo_dir/.git" ]; then
  echo "Not a git repository: $repo_dir"
  exit 1
fi

cd "$repo_dir" || exit 1

git add -A

git commit -m "$message"
