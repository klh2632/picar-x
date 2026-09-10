#!/usr/bin/env bash
set -u

repo_dir="${1:-$(pwd)}"
branch="${2:-$(git -C "$repo_dir" branch --show-current 2>/dev/null || echo main)}"
remote="${3:-origin}"
message="${4:-auto-commit: publish to GitHub}"

if [ ! -d "$repo_dir/.git" ]; then
  echo "Not a git repository: $repo_dir"
  exit 1
fi

cd "$repo_dir" || exit 1

git add -A
git commit -m "$message" || {
  echo "No local changes to commit."
  exit 0
}

git push "$remote" "$branch"
