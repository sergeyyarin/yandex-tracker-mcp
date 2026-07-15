---
name: validate-github-actions
description: Inspect and report GitHub Actions status for an existing branch, commit, or pull request. Use when checking whether already-started repository workflows pass.
---

# Validate GitHub Actions

1. Resolve the exact repository, branch, pull request, or commit requested.
2. Read the associated workflow runs and checks through GitHub without changing
   repository state.
3. If checks are still running, wait only when the user asked for monitoring;
   otherwise report the current state.
4. For failures, identify the failing workflow and job and provide its URL and
   concise error context when logs are available.
5. Report successful, pending, skipped, cancelled, and failed checks clearly.

Do not push a commit to trigger CI. Do not rerun or cancel workflows, edit
workflow files, merge pull requests, or expose secrets unless the user
explicitly requests the corresponding action.
