---
name: update-docs
description: Update and synchronize this repository's English and Russian documentation from verified current code. Use for README, configuration, architecture, tool, task-management, or changelog documentation changes.
---

# Update project documentation

1. Treat the current code, settings, packaging, and workflows as the source of
   truth. Verify commands and option names before documenting them.
2. Keep `README.md` and `README_ru.md` structurally and semantically aligned.
3. Update `docs/TASK_MANAGEMENT.md` when controlled-write or idempotent workflow
   behavior changes.
4. Document only installation artifacts and endpoints that are actually
   available. Do not describe ChatGPT Work in the browser without a public
   remote MCP endpoint and a distributable plugin.
5. Use placeholders for tokens and organization identifiers. Never copy live
   credentials, issue content, or audit data into examples.
6. Add current changes to `Unreleased` in `CHANGELOG.md`. Preserve historical
   release entries even when their terminology is obsolete.
7. Check links, fenced examples, environment-variable names, and references to
   renamed or removed files.

Do not alter code, publish artifacts, or contact external services unless the
user's documentation request explicitly requires it.
