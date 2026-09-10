#!/usr/bin/env bash
set -u

repo_dir="${1:-$(pwd)}"

if [ ! -d "$repo_dir/.git" ]; then
  echo "Not a git repository: $repo_dir"
  exit 1
fi

cd "$repo_dir" || exit 1

echo "=================================================="
echo "Repository status: $(pwd)"
echo "=================================================="

git --no-pager status --short --branch
echo

echo "--- remotes ---"
git remote -v || true
echo

echo "--- recent commits ---"
git --no-pager log --oneline -n 5 || true

echo

echo "--- branch graph ---"
git --no-pager branch -vv || true

echo

echo "--- untracked files ---"
if [ -n "$(git ls-files --others --exclude-standard)" ]; then
  git ls-files --others --exclude-standard
else
  echo "None"
fi
