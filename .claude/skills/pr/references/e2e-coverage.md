# Phase 3 — E2E coverage

Unit tests (Vitest, Django) prove a component or function in isolation. A feature is only covered when a Playwright spec drives it through the real stack: login, websocket, backend, rendered page. This phase finds every user-visible behaviour the PR adds or changes and checks that some spec exercises it.

## 1. Behaviour list

Read the PR diff and its summary. List each **behaviour** a user can see or trigger: one line per role and state, e.g. "captain on turn clicks a chat suggestion → confirm dialog opens", "teammate right-clicks own suggestion → Remove item; avatar disappears for the team". Include the negative branches the code adds (who does *not* see it, which state hides it). Backend-only, CI, docs, refactors with no visible change and pure styling (covered by Phase 4 screenshots) produce no behaviours.

## 2. Map each behaviour to a spec

For each line, find the spec that exercises it:

```bash
gh pr diff "$PR" --name-only | grep '^frontend/tests/playwright/'          # specs this PR adds or edits
grep -rln '<data-testid or ws frame type>' frontend/tests/playwright/e2e/   # existing specs
```

A behaviour counts as covered when a spec performs the action and asserts the outcome (an assertion on the testid / frame / text, not merely a page load). Record each line as **covered** (`spec file › test name`) or **gap**.

## 3. Report gaps

No gaps → one line in the report: "E2E: every behaviour covered (<specs>)".

Gaps → list them in the report and offer, per gap or as one batch:

- **Subagent writes the spec**: one subagent per PR, in its own detached worktree at the PR head (`git worktree add --detach .worktrees/pw-<n> origin/<branch>`) with its own test stack slot, so it never disturbs the PR worktree or the screenshot stacks. Brief it with the behaviour list, the testids, the closest existing spec to extend, the `testing` and `playwright` skills, headless-only runs via `just test::pw::spec <pattern>` (cd form), and: every failure is a defect in the app or the spec, never flaky; app bugs are reported, not worked around. It commits only spec files, pushes with `git push origin HEAD:<branch>`, tears down its stack, releases its slot and removes its worktree.
- **Accept the gap**: the user names a reason; write it in the PR body's test plan ("No E2E: <reason>").

For a stacked PR, the lower PR's new spec commit must reach the upper branch (merge or rebase) once pushed; note that in the report.

Phase 3 is done when every behaviour line is covered, has a dispatched subagent, or has a user-accepted reason in the PR body.
