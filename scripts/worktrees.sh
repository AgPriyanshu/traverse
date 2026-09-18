#!/usr/bin/env bash
# Cut the four agent branches for a sprint from ai-master (BRANCH.md §3).
#
#   scripts/worktrees.sh 3 characters
#
# Worktree directories are persistent across sprints — they hold .venv,
# node_modules and the model cache. Only the branches are per-sprint.
set -euo pipefail

SPRINT="${1:?usage: worktrees.sh <sprint-number> <slug>}"
SLUG="${2:?usage: worktrees.sh <sprint-number> <slug>}"
AGENTS="${AGENTS:-be1 be2 fe1 do1}"

repo_root="$(cd "$(dirname "$0")/.." && git rev-parse --show-toplevel)"
worktree_root="$(dirname "$repo_root")/traverse-wt"
mkdir -p "$worktree_root"

for agent in $AGENTS; do
  branch="ai/${agent}/sprint-${SPRINT}-${SLUG}"
  directory="${worktree_root}/${agent}"
  if [ -d "$directory" ]; then
    git -C "$directory" checkout ai-master
    git -C "$directory" merge --ff-only ai-master
    git -C "$directory" checkout -b "$branch"
  else
    git -C "$repo_root" worktree add -b "$branch" "$directory" ai-master
  fi
  echo "$agent -> $branch  ($directory)"
done

git -C "$repo_root" worktree list
