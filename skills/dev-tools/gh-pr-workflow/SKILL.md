---
name: gh-pr-workflow
description: Open, verify, and self-merge a GitHub pull request on a repo you own or have merge rights on, using the `gh` CLI end to end (no web UI). Covers the create → check → merge → confirm cycle. Triggers on "open a PR", "create a pull request", "merge this PR", "is the PR ready to merge", "merge and delete the branch", "gh pr create", "self-merge".
---

# gh PR workflow (create → check → merge → confirm)

This is the actual recurring `gh` shape found across session history (dakota.hanson,
multiple repos: `ditmar_demo_applications`, `misc_tools`, `d-team-demo-apps`): open a PR
from a feature branch, confirm it's mergeable, merge it, then verify the merge landed.
`gh pr create` is already allowlisted in `~/.claude/settings.json` — this skill is the
command shapes around it, not a replacement for permissions.

**Not for issue triage or general repo browsing.** There is no recurring `gh issue *`
pattern in history — don't reach for this skill for issue work. For browsing a repo's
files without cloning, plain `gh api repos/<owner>/<repo>/contents/<path>` ad hoc is fine;
that usage is too varied per-call to templatize.

## 1. Create

```bash
gh pr create --base main --head <branch> --title "<concise title>" --body "$(cat <<'EOF'
## Summary
- <bullet per meaningful change, not per commit>

## Test plan
- [x] <check actually run>
- [ ] <check still pending, e.g. post-deploy verification>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- `--head` is just the branch name when it's in the same repo (not a fork).
- Run from inside the repo directory so `--repo` isn't needed; pass `--repo owner/repo`
  only when invoking from elsewhere (e.g. a scratch dir).
- Body is always `## Summary` + `## Test plan` (checklist, unchecked = not yet verified)
  + the Claude Code attribution line — match the existing commit/PR attribution convention,
  don't invent a different template.

## 2. Check it's actually mergeable

```bash
gh pr view <N> --json mergeable,mergeStateStatus,state
gh pr checks <N>          # if the repo has CI; prefix with `sleep 15 &&` right after
                           # create/push so checks have started before you poll
```

Don't merge on a bare "created successfully" — `mergeable` can be `UNKNOWN` for a few
seconds after creation, and `mergeStateStatus` (e.g. `BLOCKED`) is what actually predicts
whether `gh pr merge` will succeed. If it's blocked by a required check or review, stop and
tell the user rather than looking for a way around it — merging is theirs to force, not
yours.

## 3. Merge

```bash
gh pr merge <N> --merge --delete-branch
```

`--merge --delete-branch` is the pattern used every time in this history (not squash, not
rebase — one repo used `--rebase --delete-branch` for linear history, but merge commit is
the default unless the repo convention says otherwise).

## 4. Confirm it landed

```bash
gh pr view <N> --json state,mergedAt,mergeCommit
git log origin/main --oneline -3 && git branch --show-current && git status --short
```

The `git log origin/main` + `git branch --show-current` + `git status --short` combo is
the actual habit in history — it confirms the merge commit is on `origin/main`, you're not
still sitting on the now-deleted feature branch, and the working tree is clean, in one shot.
