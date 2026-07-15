---
name: prepare-release
description: Prepare a Yandex Tracker MCP release by reviewing changes, selecting a SemVer version, updating versioned files and changelog, and validating the result. Use when the user asks to prepare a release; publication actions remain separately gated.
---

# Prepare a release

1. Read `AGENTS.md`, inspect repository status, and determine the changes since
   the previous tag. Preserve unrelated work.
2. Propose or confirm the next semantic version from the actual compatibility
   impact. Apply normal SemVer rules for the current `1.x` series.
3. Update `pyproject.toml`, `server.json`, and the OCI image tag together.
4. Move the relevant `Unreleased` notes into a new dated changelog section.
   Never rewrite previous release entries.
5. Update `uv.lock` only when version or dependency metadata requires it.
6. Verify both README files and task-management documentation against the
   release contents.
7. Run `task check`, `task test`, and packaging or workflow validation relevant
   to the release.
8. Present the resulting diff, version, checks, and any blockers.

Stop before creating a commit or tag, pushing a branch, publishing a package or
container, creating a GitHub release, or triggering external deployment unless
the user explicitly requested that specific publication action. Never read or
print release secrets.
