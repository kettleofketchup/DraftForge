export const meta = {
  name: 'feature-pipeline',
  description: 'Feature delivery pipeline: recon, reviewed spec and plan, implementation, verification, comment and sensitive-information review, then automatic PR creation',
  whenToUse: 'One feature/issue end to end. Pass args {slug, title, worktree, branch, date, request, decisions, recon:[{key,ask}], specLenses:[str], planLenses:[str], finalLenses:[str], skills, base?}.',
  phases: [
    { title: 'Recon', detail: 'parallel readers map the affected surface' },
    { title: 'Spec', detail: 'write the design doc' },
    { title: 'Spec review', detail: 'adversarial multi-lens review, then revise' },
    { title: 'Plan', detail: 'writing-plans into ordered tasks' },
    { title: 'Plan review', detail: 'adversarial multi-lens review, then revise' },
    { title: 'Execute', detail: 'implement + review each task sequentially' },
    { title: 'Verify', detail: 'full verification and final adversarial code review' },
    { title: 'PR preflight', detail: 'verify comment receipt, check final HEAD and scrub publication content' },
    { title: 'Open PR', detail: 'push reviewed HEAD, create or reuse the PR' },
    { title: 'Screenshots', detail: 'capture before/after for non-test frontend changes, verify the PR comment exists' },
  ],
}

const A = args
const WT = A.worktree
const BASE = A.base || 'origin/main'
const SPEC = `${WT}/docs/superpowers/specs/${A.date}-${A.slug}-design.md`
const PLAN = `${WT}/docs/superpowers/plans/${A.date}-${A.slug}-plan.md`

const CTX = `
You are working on DraftForge (Django + Channels backend in backend/, React/TypeScript/Vite frontend in frontend/).

FEATURE: ${A.title}

USER REQUEST (verbatim):
${A.request}

DECISIONS ALREADY MADE (do not reopen; items marked "lead's call" may be corrected only with strong code evidence):
${A.decisions}

WORKTREE: ${WT} (branch ${A.branch}). ALL reads/edits/commands happen in this worktree, never in /home/kettle/git_repos/draftforge itself (other sessions use the main checkout).
- Use absolute paths. Your shell cwd may reset between calls. A compound \`cd X && cmd\` is blocked by a hook unless you append \` # allow-cd\`; use \`git -C ${WT} ...\` for git, \`npm --prefix ${WT}/frontend ...\` for npm, and \`cd ${WT} && just ... # allow-cd\` for just recipes.
- Backend tests: \`cd ${WT} && just test::run 'python manage.py test <labels> -v 2' # allow-cd\`. Never raw docker compose (use \`just test::compose\`). If containers fail with EACCES / readonly database under rootless podman, run \`setfacl -R -m u:100999:rwX -m d:u:100999:rwX ${WT}/backend ${WT}/frontend\` and restart frontend, backend AND nginx.
- Frontend unit tests: scope Vitest runs to the files you touched, with --maxWorkers=2 (parallel full suites oversubscribe the host). Typecheck with the frontend's npm typecheck script.
- Playwright: \`cd ${WT} && just test::upd # allow-cd\` then \`just test::pw::spec <specific-file-pattern>\` (pattern matches the absolute path, so use a distinctive file name). Never headed browsers. The test stack can mount a different worktree's code: grep your edit inside the container before trusting local Playwright.
- Shared test Redis: other worktrees may run tests concurrently; check for parallel df-backend-run-* containers before debugging WS test failures.
- Celery loads only MODEL_APPS; no module-level cross-app model imports in signals/ready(). Run app.tests.test_celery_settings after touching models/signals/apps.
- Cacheops: verify whether a model is cached against the CACHEOPS block in backend/backend/settings.py, not skill snippets.
- Project conventions: imports at module top; type-annotate all new/touched Python (PEP 604/585); keep comments terse (default none); structured logging with system=/subsystem= (logging skill); frontend logging via \`import { getLogger } from '~/lib/logger'\`; brand components/tokens (brand skill: PrimaryButton/SecondaryButton, no raw palette colors, UserAvatar); API binding via the api skill (Zod schemas, TanStack Query); never call a test failure flaky; surface pre-existing bugs rather than silently working around them.
- docs/superpowers/ is gitignored: spec and plan stay local, NEVER \`git add -f\` them. User-facing docs go under docs/ (mkdocs; build with \`just docs::build\`, never \`uv run mkdocs\`). A changelog.d/ fragment is required (changelog skill).
- Commits: conventional style (e.g. "feat(herodraft): ..."). ABSOLUTELY NO AI attribution of any kind (no Co-Authored-By, no Claude links, no "generated" lines). Do not push or open PRs during implementation/review. Only the final Open PR agent may publish, after PR preflight approves the exact HEAD. Honor explicit no-push/no-PR requests and tool approvals.
- Use relevant skills via the Skill tool wherever they apply. Suggested for this feature: ${A.skills}.
`

const FG = `\nRUN LONG COMMANDS (backend suites, Playwright, docs build) IN THE FOREGROUND with a Bash timeout up to 600000 ms; never end your turn while waiting on a background command or monitor. You MUST finish by calling StructuredOutput, even if some checks are incomplete (say which in your report).`
const fgOn = i => A.fgFromIndex === undefined || i >= A.fgFromIndex
const REPORT = { type: 'object', properties: { report: { type: 'string' } }, required: ['report'] }
const FINDINGS = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: { type: 'object', properties: {
      severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
      title: { type: 'string' }, detail: { type: 'string' }, evidence: { type: 'string' }, fix: { type: 'string' },
    }, required: ['severity', 'title', 'detail', 'evidence', 'fix'] } },
  },
  required: ['findings'],
}
const TASKS = {
  type: 'object',
  properties: {
    path: { type: 'string' },
    tasks: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' }, title: { type: 'string' }, summary: { type: 'string' },
    }, required: ['id', 'title', 'summary'] } },
    notes: { type: 'string' },
  },
  required: ['path', 'tasks'],
}
const TASK_RESULT = { type: 'object', properties: {
  status: { type: 'string', enum: ['done', 'blocked'] }, commits: { type: 'array', items: { type: 'string' } },
  testsRun: { type: 'string' }, notes: { type: 'string' },
}, required: ['status', 'commits', 'testsRun', 'notes'] }
const REVIEW = { type: 'object', properties: {
  approved: { type: 'boolean' },
  issues: { type: 'array', items: { type: 'object', properties: {
    severity: { type: 'string', enum: ['blocker', 'major', 'minor'] }, detail: { type: 'string' }, fix: { type: 'string' },
  }, required: ['severity', 'detail', 'fix'] } },
}, required: ['approved', 'issues'] }

phase('Recon')
const recon = await parallel(A.recon.map(r => () => agent(
  `${CTX}\nRECON TASK (${r.key}) — read-only, do not edit anything. ${r.ask}\nReturn a dense, factual markdown report with file:line evidence. No recommendations beyond what the facts imply.`,
  { label: `recon:${r.key}`, phase: 'Recon', schema: REPORT, agentType: 'Explore' })))
const reconText = recon.map((r, i) => `## Recon: ${A.recon[i].key}\n${r ? r.report : '(agent failed — re-derive yourself)'}`).join('\n\n')

phase('Spec')
const specOut = await agent(
  `${CTX}\nUse the superpowers:brainstorming skill's "Written Design" guidance (the user has opted out of further questions; do not ask any — you are writing the design doc). Write the full design doc to ${SPEC}. Cover: intent and why; goals, non-goals, anti-goals; constraints; Approaches (2-3 real alternatives grounded in the code, with trade-offs and the chosen one and why); data model and migrations; backend API/WebSocket protocol (message shapes, authorization rules, channel-layer groups); frontend components, state and interactions with text mockups; security/privacy model with an explicit threat list and how each threat is closed; test strategy (backend unit/consumer tests, Vitest, Playwright E2E, populate data); docs + changelog; what is left to the builder; decisions marked as the lead's call. Ground every claim in the recon below; verify anything uncertain by reading code.\n\n${reconText}\n\nReturn a short summary of the doc and any open risks.`,
  { label: 'write-spec', phase: 'Spec', schema: REPORT })

phase('Spec review')
const specFindings = await parallel(A.specLenses.map((lens, i) => () => agent(
  `${CTX}\nYou are an ADVERSARIAL reviewer of the design doc at ${SPEC}. Assume it is wrong until proven otherwise. Lens: ${lens}\nRead the doc and the code. Report only defects you can back with evidence (file:line or a concrete scenario). Empty list if none survive your own scrutiny.`,
  { label: `spec-review:${i + 1}`, phase: 'Spec review', schema: FINDINGS })))
const specIssues = specFindings.filter(Boolean).flatMap(f => f.findings)
log(`Spec review: ${specIssues.length} findings (${specIssues.filter(f => f.severity === 'blocker').length} blockers)`)
const specRevised = await agent(
  `${CTX}\nRevise the design doc at ${SPEC} using these adversarial review findings. For each, independently verify it against the code first; apply real ones, reject wrong ones. Append a "Review log" section listing each finding with applied/rejected and why.\n\nFINDINGS:\n${JSON.stringify(specIssues, null, 2)}\n\nReturn a summary of changes and anything that genuinely needs the user's decision (only if the answer changes what gets built).`,
  { label: 'spec-revise', phase: 'Spec review', schema: REPORT })

phase('Plan')
await agent(
  `${CTX}\nInvoke the superpowers:writing-plans skill and write the implementation plan for the design at ${SPEC} to ${PLAN}. Constraints: tasks are executed SEQUENTIALLY by fresh subagents in the same worktree, each ending with a commit and a green relevant test subset; the tree must build, typecheck and migrate cleanly after every task; tests come first in each task (TDD); include exact files, commands, and verification per task; the final tasks cover Playwright E2E, docs, changelog fragment, and full verification. Keep tasks to roughly 8-14. Return the plan path and the ordered task list.`,
  { label: 'write-plan', phase: 'Plan', schema: TASKS })

phase('Plan review')
const planFindings = await parallel(A.planLenses.map((lens, i) => () => agent(
  `${CTX}\nYou are an ADVERSARIAL reviewer of the implementation plan at ${PLAN} (design: ${SPEC}). Assume it is wrong until proven otherwise. Lens: ${lens}\nReport only evidence-backed defects.`,
  { label: `plan-review:${i + 1}`, phase: 'Plan review', schema: FINDINGS })))
const planIssues = planFindings.filter(Boolean).flatMap(f => f.findings)
log(`Plan review: ${planIssues.length} findings`)
const plan = await agent(
  `${CTX}\nRevise the plan at ${PLAN} using these adversarial findings; verify each against the code first, apply real ones, reject wrong ones, and append a "Review log". Then return the final ordered task list.\n\nFINDINGS:\n${JSON.stringify(planIssues, null, 2)}`,
  { label: 'plan-revise', phase: 'Plan review', schema: TASKS })

phase('Execute')
const results = []
let blocked = null
for (const [ti, t] of plan.tasks.entries()) {
  const fg = fgOn(ti) ? FG : ''
  let res = await agent(
    `${CTX}\nYou are implementing ONE task of the plan at ${PLAN} (design: ${SPEC}). Use superpowers:test-driven-development and superpowers:verification-before-completion before reporting. Task ${t.id}: ${t.title}\n${t.summary}\nRead the plan section for this task in full. Do exactly that task, run its verification, commit (no AI attribution). If blocked by something outside the task, report status=blocked with details instead of improvising.\nPrior tasks:\n${results.map(r => `${r.id}: ${r.status} ${r.notes}`).join('\n')}${fg}`,
    { label: `impl:${t.id}`, phase: 'Execute', schema: TASK_RESULT })
  if (!res || res.status === 'blocked') { blocked = { task: t, res }; break }
  for (let round = 0; round < 2; round++) {
    const rev = await agent(
      `${CTX}\nReview task ${t.id} ("${t.title}") of ${PLAN}, implemented in commits ${res.commits.join(', ')} in ${WT}. Check spec compliance (${SPEC}) and code quality (project conventions above). Be adversarial: run the task's verification yourself, grep for missed sites. Approve only if no blocker/major issues.${fg}`,
      { label: `review:${t.id}:${round + 1}`, phase: 'Execute', schema: REVIEW })
    if (!rev || rev.approved) break
    res = await agent(
      `${CTX}\nFix these review issues for task ${t.id} ("${t.title}") of ${PLAN} in ${WT}, re-run verification, commit (no AI attribution):\n${JSON.stringify(rev.issues, null, 2)}${fg}`,
      { label: `fix:${t.id}:${round + 1}`, phase: 'Execute', schema: TASK_RESULT })
    if (!res || res.status === 'blocked') { blocked = { task: t, res }; break }
  }
  if (blocked) break
  results.push({ id: t.id, ...res })
}

let finalReview = null, verification = null, finalIssues = [], finals = []
if (!blocked) {
  phase('Verify')
  await agent(
    `${CTX}\nRun \`git -C ${WT} fetch origin\` and merge ${BASE} into ${A.branch} (plain merge, no AI attribution). Resolve conflicts preserving both sides' intent; if a migration number collides, renumber ours. Report what you merged and fixed.${FG}`,
    { label: 'merge-base', phase: 'Verify', schema: REPORT })
  verification = await agent(
    `${CTX}\nRun the full verification for the branch in ${WT} (superpowers:verification-before-completion): full backend suite in every CI group (labels from \`just ci::backend-test-labels app\`, \`... migrations\` and \`... rest\`), makemigrations --check --dry-run, app.tests.test_celery_settings, frontend typecheck + lint + lint:shadcn + the FULL Vitest suite exactly as CI runs it (with --maxWorkers=2; new imports can break unrelated suites through import cycles), the new Playwright spec(s) via just test::pw::spec, \`just docs::build\`, pre-commit on changed files. Report exact commands and outcomes. Do not fix anything; report failures with output.${FG}`,
    { label: 'verify:full', phase: 'Verify', schema: REPORT })
  finals = await parallel(A.finalLenses.map((l, i) => () => agent(
    `${CTX}\nADVERSARIAL final review of the whole branch diff (\`git -C ${WT} diff ${BASE}...HEAD\`), lens: ${l}. Verification report:\n${verification ? verification.report : 'n/a'}\nReport only evidence-backed defects.${FG}`,
    { label: `final-review:${i + 1}`, phase: 'Verify', schema: FINDINGS })))
  finalIssues = finals.filter(Boolean).flatMap(f => f.findings).filter(f => f.severity !== 'minor')
  if (finalIssues.length) {
    finalReview = await agent(
      `${CTX}\nVerify then fix these final-review findings in ${WT} (reject false ones with reasons), re-run affected verification, commit (no AI attribution):\n${JSON.stringify(finalIssues, null, 2)}${FG}`,
      { label: 'final-fix', phase: 'Verify', schema: TASK_RESULT })
  }
  const comments = await agent(
    `Review the comments on branch ${A.branch} against ${BASE} in the worktree ${WT}. Use absolute paths and worktree-scoped commands. Prefer terse comments; remove plan/task references. Commit any edits in the worktree as "chore: tighten comments" with no AI attribution, do not push, and write the gate receipt for the final HEAD of this branch.`,
    { label: 'comment-review', phase: 'Verify', agentType: 'comment-reviewer:comment-reviewer' })
  const summary = { spec: SPEC, plan: PLAN, specOut, specRevised, results, verification, finalIssues, finalReview, comments, minor: finals.filter(Boolean).flatMap(f => f.findings).filter(f => f.severity === 'minor') }
  if (!verification || !comments || finals.some(f => !f) || (finalIssues.length && (!finalReview || finalReview.status !== 'done'))) {
    return { ...summary, blocked: { stage: 'PR preflight', reason: 'Verification, final review or comment review is incomplete; nothing published.' } }
  }
  phase('PR preflight')
  const preflight = await agent(
    `${CTX}\nPrepare automatic PR publication, but DO NOT push or call gh pr create/edit/comment. Honor any explicit no-push/no-PR instruction. Use cd into ${WT} for every worktree command. Verify the expected branch, clean index/tree, no in-progress git operation, and the actual final HEAD. Validate the comment-review gate receipt against that HEAD; missing/stale/failed receipt blocks publication. Review the verification evidence below and rerun checks affected by final fixes or comment edits. Missing/failed required checks or unresolved major findings block publication; do not assume a status=done means tests passed.\n\nIndependently review ALL outgoing commits since ${BASE}, including commit messages and intermediate versions, the final diff, filenames, docs, changelog, fixtures, comments, and any proposed PR title/body for sensitive information. Check credentials/tokens/private keys, personal/contact details, private partner/org/bot/chat identities, internal endpoints and copied logs/screenshots. Use local tools only; never send suspect content to scanners or reproduce secret values in the report. Do not rewrite history or silently redact intended behaviour: block and report only safe file/line references if anything needs remediation. Verify no prohibited attribution is present. Do not stage ignored specs/plans or unrelated files.\n\nPrepare a factual PR title using the feature title and commits (no title question needed), and a body with Summary, Test plan, truthful verification results and Closes #N only for the actual originating issue. Use a unique mktemp directory and Write for the body file. If this branch depends on an unmerged PR, mark draft=true. Run 'git -C ${WT} diff --name-only ${BASE}...HEAD | ${WT}/.claude/skills/pr/scripts/frontend-screenshot-gate.sh'; when it prints files, the Test plan must list "Before/after screenshots posted on the PR" as an open item, never claim none are needed. Review the completed title/body for sensitive content too. Approve only when all checks pass; return the exact reviewed HEAD and body path.\n\nVerification: ${JSON.stringify(verification)}\nFinal findings: ${JSON.stringify(finalIssues)}\nFinal fixes: ${JSON.stringify(finalReview)}\nComment review: ${comments}${FG}`,
    { label: 'pr-preflight', phase: 'PR preflight', schema: { type: 'object', properties: {
      approved: { type: 'boolean' }, head: { type: 'string' }, title: { type: 'string' }, bodyPath: { type: 'string' }, draft: { type: 'boolean' }, report: { type: 'string' },
    }, required: ['approved', 'head', 'title', 'bodyPath', 'draft', 'report'] } })
  if (!preflight || !preflight.approved) {
    return { ...summary, preflight, blocked: { stage: 'PR preflight', reason: 'Publication was not approved; nothing published.' } }
  }
  phase('Open PR')
  const publication = await agent(
    `${CTX}\nYou are the sole Open PR publication agent. The user has authorized automatic push and PR creation after successful comment and sensitive-information review; do not ask again unless an explicit no-push/no-PR request or a real blocker applies. Use the pr and github skills. Work only in ${WT}, branch ${A.branch}. Preflight approval: ${JSON.stringify(preflight)}.\n\nBefore any publication, verify HEAD still equals the approved hash, the tree/index are clean, the comment gate receipt remains valid, origin is the intended repository, and the title/body file contents still match the reviewed material (if uncertain, re-review them locally). Any code/history/body changes invalidate approval: stop rather than publish. Do not add commits or change code. Check for an existing PR for this repository and exact head branch before pushing; reuse an OPEN PR, but stop and report a MERGED/CLOSED one instead of reopening or duplicating it. Never force-push or bypass hooks. Push only the reviewed feature branch, then verify its remote OID still matches approved HEAD. Create the PR with the approved title and --body-file, --base main and the explicit head branch; use --draft when preflight.draft is true. If creation reports a duplicate, query and reuse the existing PR. Report the URL and any actual auth/hook failure, without blind retries. Never merge the PR. Run 'git -C ${WT} diff --name-only ${BASE}...HEAD | ${WT}/.claude/skills/pr/scripts/frontend-screenshot-gate.sh' and return its output lines as screenshotFiles ([] when it exits 1). Do not capture screenshots or post any screenshot comment; the Screenshots phase does that. Do not start a session-only monitor inside this short-lived agent. Return the PR URL/number/head.${FG}`,
    { label: 'open-pr', phase: 'Open PR', schema: { type: 'object', properties: {
      status: { type: 'string', enum: ['opened', 'reused', 'blocked'] }, url: { type: 'string' }, number: { type: 'integer' }, head: { type: 'string' },
      screenshotFiles: { type: 'array', items: { type: 'string' } }, report: { type: 'string' },
    }, required: ['status', 'url', 'number', 'head', 'screenshotFiles', 'report'] } })
  if (!publication || publication.status === 'blocked') return { ...summary, preflight, publication, monitoringHandoff: null }
  const n = publication.number
  const shots = publication.screenshotFiles || []
  phase('Screenshots')
  let capture = null
  if (shots.length) {
    capture = await agent(
      `${CTX}\nYou are the Screenshots agent for PR #${n} (${publication.url}), head worktree ${WT}. The diff changes non-test frontend code: ${shots.join(', ')}. Use the pr skill and follow ${WT}/.claude/skills/pr/references/screenshots.md end to end: a shot list covering every changed file (for files with no UI of their own, the pages and states that run them), before from the merge-base in a detached base worktree, after from ${WT}, headless capture on each worktree's own test stack slot, every PNG viewed, images on the pr-assets/${n} branch, ONE "## Screenshots" comment. For this phase you are authorized to push the pr-assets/${n} branch and comment on PR #${n}; do not push the feature branch, change code or touch other PRs. Tear down both stacks and release both slots, also on failure. If capture cannot finish (no free slot, stack failure), post "Screenshots pending: <reason>" instead and return status=pending. Never post a "No screenshots:" comment on this PR.${FG}`,
      { label: 'screenshots', phase: 'Screenshots', schema: { type: 'object', properties: {
        status: { type: 'string', enum: ['posted', 'pending'] }, commentUrl: { type: 'string' }, report: { type: 'string' },
      }, required: ['status', 'commentUrl', 'report'] } })
  }
  const listed = shots.slice(0, 5).join(', ') + (shots.length > 5 ? ', ...' : '')
  const fallback = shots.length
    ? `Screenshots are REQUIRED (non-test frontend files: ${shots.join(', ')}). If kind is none or skip, post exactly one comment: gh pr comment ${n} --body "Screenshots pending: this PR changes non-test frontend code (${listed}); before/after capture did not complete." and return kind=pending.`
    : `No non-test frontend code changed. If kind is none, post exactly one comment: gh pr comment ${n} --body "No screenshots: this PR changes no non-test frontend code." and return kind=skip.`
  const shotCheck = await agent(
    `Work in ${WT}. Run gh pr view ${n} --json comments. Classify the newest comment whose body starts with "## Screenshots" (kind=screenshots), "No screenshots:" (kind=skip) or "Screenshots pending:" (kind=pending); kind=none when there is none. ${fallback} Post nothing else. Return the kind and the comment URL. No AI attribution.`,
    { label: 'screenshot-check', phase: 'Screenshots', schema: { type: 'object', properties: {
      kind: { type: 'string', enum: ['screenshots', 'skip', 'pending', 'none'] }, commentUrl: { type: 'string' },
    }, required: ['kind', 'commentUrl'] } })
  const shotsDone = !!shotCheck && (shots.length ? shotCheck.kind === 'screenshots' : shotCheck.kind !== 'none')
  const incomplete = shotsDone ? [] : ['screenshots']
  const screenshots = shotsDone
    ? (shots.length ? 'Screenshots: before/after comment posted; re-run /pr Phase 4 after any later commit that touches non-test frontend code.' : 'Screenshots: none required (no non-test frontend code changed).')
    : `Screenshots PENDING and REQUIRED for ${shots.join(', ') || 'this PR'}: capture and post the before/after comment via /pr Phase 4 first; the PR is not ready until it exists.`
  const monitoringHandoff = `Coordinator: in the parent session, invoke /pr for PR #${n} (${publication.url}) from ${WT}. Push and PR creation are already authorized for this branch. Run its E2E coverage and CI phases, and arm the 30-minute progressive CI/CD and main merge-conflict monitor, re-arming each window until the PR is merged or closed. ${screenshots}`
  return { ...summary, preflight, publication, capture, shotCheck, screenshotsRequired: shots.length > 0, incomplete, monitoringHandoff }
}
return { spec: SPEC, plan: PLAN, specOut, specRevised, results, blocked }
