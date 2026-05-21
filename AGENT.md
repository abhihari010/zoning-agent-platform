# Agent Notes

- Keep local agent skills and private tool config out of Git. `.agents/`, `.codex/`, and `skills-lock.json` are intentionally ignored.
- Work from the current spec, handoff notes, and open GitHub issues before starting new implementation.
- After completing a set of issues, commit and push the branch, then review the branch against `main` for scope, tests, private files, and merge conflicts.
- If the branch is clean, tests pass, and GitHub reports no conflicts, merge the PR before starting the next issue batch.
- Prefer small, focused branches and PRs tied to issue numbers. Close completed issues only after the relevant branch is verified or merged.
- Before a new conversation continues the work, check branch status, open PRs, open issues, and the latest handoff/spec files.
