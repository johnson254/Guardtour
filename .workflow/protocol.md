# Worktree Protocol

## Branch Layout
- `main` — only approved work. Protected. No agent pushes directly.
- `work/frontend` — frontend agent (htmx, routes.html, JS unification)
- `work/backend` — backend agent (api/, runtime fixes)
- `review/YYYY-MM-DD-HHMM-<slug>` — temporary branch created when an agent finishes a logical chore so we can inspect the diff before approval. Delete after merge or squash.

## Agent Rules
1. Agents push ONLY to their assigned `work/*` branch.
2. Before pushing, rebase onto the latest `work/*`.
3. DO NOT merge. DO NOT push to `main`.
4. Commit messages follow Conventional Commits: `feat:`, `fix:`, `chore:`, `refactor:`, `style:`, `test:`, `docs:`.
5. Each agent run must leave a marker file: `<branch>-latest.md` with:
   - Branch name
   - Last commit SHA
   - Files touched
   - One-line summary of what changed and what we should verify
6. Do not amend or rewrite published history on shared branches.

## Review / Approval Rules (Jay)
1. Each marker file is inspect-able via Nexus at `http://localhost:4747`.
2. Approval is one of:
   - `merge <branch>` — clean squash/merge to main
   - `fix <branch> <note>` — send back to agent with note
   - `drop <branch>` — force-push drop
3. Only after approval do we fast-forward `main`.

## Interaction With Nexus
- Read `frontend-latest.md` and `backend-latest.md` from repo root.
- Show last commit, diff stat, and changed file list.
- Flag any modified files that overlap with other agent domains.
