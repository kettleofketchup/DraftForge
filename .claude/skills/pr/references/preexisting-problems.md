# Pre-existing problems → issues and fix PRs

Work on a branch often turns up bugs that were already on `main`: a test that fails
there too, a broken management command, a behaviour the spec chose not to change. They
are not this PR's job, but they must not be dropped either.

## 1. Collect

Gather every problem the branch's work found that is **not caused by the branch**:

- verification failures that also fail on `origin/main`
- "pre-existing" / "reported only" items in spec, plan, review or verification reports
- reviewer findings marked pre-existing or out of scope
- open problems from this branch that were deferred rather than fixed

For each, confirm it on `origin/main` (read the code there, or run the failing test
there) and record `file:line` evidence. Drop anything you cannot confirm.

## 2. Present

Show the user every confirmed problem, oldest-bug-first is fine, one line each with
evidence. Then ask (`AskUserQuestion`, `multiSelect: true`) which to act on. For each
problem the options are:

- **Issue only**: file a GitHub issue.
- **Issue + fix PR**: file the issue, then a subagent fixes it in its own worktree and
  opens a PR that closes the issue. Use a workflow instead of a single subagent when the
  fix spans several areas.
- **Fix in this PR**: only for problems this branch introduced or that are one-line
  and squarely in its area.
- **Skip**.

Never file issues or open PRs without the user's pick: the repo is public.

## 3. Review for sensitive information before `gh issue create`

Write each issue body to a temp file and check it before filing. Remove:

- secrets, tokens, keys, env values, connection strings
- production hostnames, IPs, SSH targets, server paths
- user data: usernames, nicknames, Discord/Steam IDs, emails, real MMR values of people
- partner org names, their bots, chat participants
- internal tool names that must not appear on GitHub (see memory)
- local machine paths (`/home/...`, worktree names)
- any AI attribution

Keep bodies to code facts: what is wrong, `file:line`, how to reproduce, expected vs
actual, suggested fix. Label with the existing labels (`bug`, `backend`, `frontend`, …).

```bash
gh issue create --title "<type(scope): problem>" --label bug --label backend --body-file "$tmp"
```

## 4. Fix PRs

One problem per worktree, branch and PR, based on `origin/main`:

```bash
git worktree add .worktrees/fix-<slug> -b fix/<slug> origin/main
```

Brief the subagent with absolute worktree paths (its cwd resets between calls), the
issue number, the evidence, and TDD + verification skills. The PR body must contain a
closing keyword on its own line so merging into `main` closes the issue:

```markdown
Closes #<issue>
```

Add a changelog fragment if the fix is user- or operator-visible. In the original
feature PR, reference the issues under a `## Related` heading **without** a closing
keyword (`Related: #<issue>`), so merging the feature does not close them.
