# CI Runners

Almost every CI job runs on GitHub-hosted runners. One job, `playwright.yml` `prepare`,
can run on a self-hosted runner in the home Kubernetes cluster (label
`draftforge-home`), and only for pull requests from allowlisted authors on branches in
this repo. It builds the dev images and the test database once per content hash instead
of once per test job. Test jobs pick up its output if it is ready and otherwise do what
they do today.

The cluster side (ARC runners, BuildKit, Zot) lives in the home GitOps repo:
`apps/github-runners`, `apps/buildkit`, `apps/zot`, and the human runbook
`docs/runbooks/github-runners.md`. Merging there deploys.

!!! warning "Everything here is off until a human sets the repo variables"
    With `SELF_HOSTED_RUNNERS` unset, `prepare` is skipped and `HOME_PREPARE` is
    `false`, so every job runs on hosted runners exactly as before. See
    [Human actions](#human-actions-in-order).

## What runs where

| Job | Where | Reason |
|---|---|---|
| `playwright/prepare` | Home runner for allowlisted same-repo PRs; skipped otherwise | Builds missing dev images and the test DB once per hash, off the critical path |
| 15 stack jobs (chromium ×4, mobile ×2, herodraft ×2, layout, events ×2, org-features, backend ×3) and `unit` | GitHub | Execution-bound; the home cluster is far too small to run them |
| `preview-images/build` | GitHub | A 2-runner pool would saturate on every push and `npm run build` is uncached; it reads `main`'s GHCR `:buildcache` read-only instead |
| `preview-images/report` (`pull_request`), `preview-queue` (`pull_request_target`, `workflow_run`) | GitHub | Write permissions |
| `build-docker-images` | GitHub | Pushes prod `:latest` and GHCR `:buildcache`; trusted builds never touch the shared daemon |
| `build-test-db` | GitHub | No BuildKit benefit; daemon-only commands |
| `release-docker-images` | GitHub, `--no-cache` | Release artifacts |
| `record-demos`, changelog, shellcheck, format, shadcn-lint, docs, helm-chart, labelers | GitHub | Write permissions or too short to matter |

## The kill switch and the allowlist

Two repository variables (Settings → Secrets and variables → Actions → Variables):

| Variable | Value | Effect |
|---|---|---|
| `SELF_HOSTED_RUNNERS` | `true` to enable; unset or anything else to disable | The kill switch. Unset means `prepare` is skipped and test jobs never look for its output. |
| `HOME_RUNNER_AUTHORS` | Comma-separated GitHub logins, default `kettleofketchup` | Who may use the home runner. Both the PR author and the triggering actor must be listed. |

`HOME_RUNNER_AUTHORS` must stay equal to the home repo's
`apps/github-runners/manifests/hooks/allowed-authors` (one login per line). The
runner's job-started hook reads that file and is authoritative: if the two differ, the
hook wins and refuses the job.

`prepare` runs only when all of these hold (the same predicate is the workflow-level
`HOME_PREPARE` env that test jobs read):

```yaml
if: >-
  vars.SELF_HOSTED_RUNNERS == 'true'
  && github.event_name == 'pull_request'
  && github.event.pull_request.head.repo.full_name == github.repository
  && contains(format(',{0},', vars.HOME_RUNNER_AUTHORS), format(',{0},', github.event.pull_request.user.login))
  && contains(format(',{0},', vars.HOME_RUNNER_AUTHORS), format(',{0},', github.triggering_actor))
```

Bot authors and bot pushes onto a human PR fail the author or actor check. Forks fail
the same-repo check. Pushes to `main`, tags and dispatches are not `pull_request`.

## What `prepare` does

1. **Hashes** each item: `frontend-dev`, `backend-dev` and `nginx` via
   `scripts/hash-docker-image.sh`, `test-db` via `scripts/hash-test-db-sources.sh`.
2. **Fast path** (`just ci::prepare-missing <pr>`): an item is present when the trusted
   `draftforge/<img>:<hash>` or this PR's `draftforge-ci/<img>:pr-<n>-<hash>` exists on
   GHCR. If nothing is missing the job ends in about 30 s, before any toolchain install.
3. **Build what is missing** through the home BuildKit (`setup-builder` composite, remote
   buildx driver, no Docker daemon on the runner): dev images with
   `docker::<svc>::build-dev --mode=pr --pr=<n>`, the test DB with
   `just db::populate::fresh` then `docker::db::build --mode=pr --pr=<n>`.

Permissions: `contents: read`, `packages: write`. Timeout 15 minutes.

### Why tests never `needs: prepare`

A `needs` edge would put a 2-runner pool in front of every test job. Instead the test
jobs start at once and run today's setup (toolchain, Node, Playwright deps). Then, when
`HOME_PREPARE` is `true`:

- `just docker::pr-pull <pr> 180` uses `draftforge/<img>:<hash>` if it is already local,
  and otherwise polls GHCR for `draftforge-ci/<img>:pr-<n>-<hash>` for up to 180 s in
  total (one deadline for all three images), pulls it and retags it `:latest` and
  `:<hash>`.
- `just docker::db::pr-pull <pr>` tries the prepared test DB once, with no wait: a local
  populate takes about 51 s, so waiting never pays.

`prepare` is not a required check, and `scripts/check-runs-on.sh` fails if any job lists
it in `needs`.

### Failure behaviour

| Situation | Cost to a test job |
|---|---|
| Kill switch off, or author not allowlisted | Nothing; `prepare` is skipped and `HOME_PREPARE` is `false` |
| Pool down, Pending, saturated, or `prepare` failed | At most 180 s, and only on PRs where the trusted image for the current hash does not exist yet (lockfile or Dockerfile changes); then today's local build |
| Prepared image exists but does not pull (for example a package-permission error, see H-R5) | A `::warning::`, then today's local build |
| Prepared test DB missing | Nothing; local populate as today |
| Kill switch flipped while `prepare` jobs are queued | The next push cancels them (the playwright concurrency group cancels in progress); cancel the rest by hand |

On lockfile PRs `prepare` uploads roughly 600 MB per dev image from the home uplink. If
that upload alone exceeds the 180 s budget, tests fall back by design and Phase 2 buys
nothing for that case; canary (a) in the home runbook measures it.

## Cache and image names

| Name | Written by | Read by |
|---|---|---|
| `ghcr.io/kettleofketchup/draftforge/<img>:latest`, `:<hash>`, `:<version>` | Trusted hosted workflows and release tags | Everyone |
| `ghcr.io/kettleofketchup/draftforge/<img>:buildcache` | Trusted hosted builds only (`--mode=trusted --push`) | Trusted builds, preview builds, PR `prepare` (read-only) |
| `ghcr.io/kettleofketchup/draftforge-ci/<img>:pr-<n>-<hash>`, `draftforge-ci/test-db:pr-<n>-<hash>` | PR `prepare` only | That PR's test jobs |
| Zot `zot.zot.svc.cluster.local:5000/buildcache/pr/draftforge/<img>:pr-<n>` | PR `prepare`, with the `ci` credential | PR `prepare` (BuildKit only) |

Zot is plain HTTP on a ClusterIP. Only BuildKit talks to it; client-side tools
(`imagetools`, `docker login`, `docker pull`) assume HTTPS and must not target it.
`just ci::zot-auth` writes its credential straight into the docker client config, and
the buildx session forwards it to BuildKit.

**Trusted** means
`github.ref == 'refs/heads/main' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')`.
`build-docker-images` and `build-test-db` run only under that condition. Release tags
also publish `draftforge/*` (see below). Dispatches from other refs never run trusted
mode and never run `prepare`.

**Enforced:**

- No fork, bot, non-allowlisted author or non-PR event runs on a home runner (the
  job-started hook plus the fork approval policy, H-R2).
- Dockerfile `RUN` steps cannot write Zot: anonymous access is read-only.
- Nothing produced on the home cluster is read by `main`, tags or releases.
- Releases build with `--no-cache` and ignore `:buildcache`.

### Accepted by trust

These are known and not prevented:

- **Allowlisted authors share build state.** They share BuildKit's local cache, its
  `RUN --mount=type=cache` ids (Poetry, npm) and the Zot `ci` credential, so one
  allowlisted PR can influence another's builds.
- **Tag pushes are trusted writers of `draftforge/*` tags** (`:latest`, `:<hash>`,
  `:<version>`, and `backend-dev`, which the backend release recipe also builds).
  Releases build with `--no-cache`, but they still publish. A tag ruleset limits who
  can push release tags (human action 4 below).
- **`ZOT_CI_PASSWORD` reaches every same-repo workflow run**, not only `prepare`: it is
  a repo Actions secret. That is acceptable because Zot is reachable only from inside
  the home cluster and the credential's only grant is `buildcache/pr/**`.
- **Collaborators on an allowlisted PR.** A non-allowlisted write collaborator can push
  commits to an allowlisted author's PR branch. The hook refuses that push's run, but
  those commits run on the home pool after the author's next push.
- **Same-repo writers can still push to `draftforge/*` from a hosted PR job** by editing
  a workflow, as today. Default token permissions `read` (H-R6) narrows this, but a
  workflow can still request `packages: write`.
- **Tests on `main` pull `draftforge/*:<hash>` by tag existence**, as today. Provenance
  attestations are a follow-up.

## `docker::buildx` modes

`just/docker/mod.just` `buildx` (called by every `docker::<svc>::build*` recipe) has two
explicit modes. Appending flags to one mode is not enough; the PR mode drops every
trusted tag.

| | `--mode=trusted` (default) | `--mode=pr --pr=<n>` |
|---|---|---|
| Used by | Hosted `main` and release workflows, local builds | Home `prepare` only |
| Tags | `draftforge/<img>:latest`, `:<hash>` (plus `:<version>` with `--release`) | Only `draftforge-ci/<img>:pr-<n>-<hash>` |
| Cache from | GHCR `:buildcache` (none with `--no-cache`) | Zot `buildcache/pr/draftforge/<img>:pr-<n>`, then GHCR `:buildcache` |
| Cache to | GHCR `:buildcache` with `--push` (none with `--no-cache`) | Zot per-PR cache only, `ignore-error=true` |
| Output | `--push`, or `--load` | Always `--push`, never `--load` |
| Rejects | `--pr` | `--release`, `--no-cache` |

Both add `--platform linux/amd64`, and `--provenance=false` (trusted mode skips it under
podman, whose buildx shim rejects it). `docker::db::build --mode=pr --pr=<n>` builds the
busybox test-DB image through buildx and pushes only
`draftforge-ci/test-db:pr-<n>-<hash>`, with no daemon commands. The recipe tests in
`scripts/slot_tests/test_docker_recipes.py` stub `docker` and assert that PR mode emits
no `draftforge/` tag, no `:latest` and no GHCR `cache-to`.

## The `runs-on` guard is not a security control

`scripts/check-runs-on.sh` (`just ci::check-runs-on`, the `runs-on-guard` job in
`shellcheck.yml`) fails when `draftforge-home` appears in any job other than
`playwright.yml` `prepare`, when that job lacks `timeout-minutes` or any clause of the
`if` above, when a workflow using the label triggers on `pull_request_target` or
`workflow_run`, or when any job `needs: prepare`.

It catches mistakes by trusted authors. On `pull_request` GitHub runs the PR head's copy
of the workflows, so a fork can write `runs-on: draftforge-home` on any job and edit the
guard too. The boundary is, in order: the runner's job-started hook in the home repo,
which rejects anything but an allowlisted same-repo PR whatever the workflow says; the
fork approval policy (H-R2); and the runner pod's network and resource limits.

## Phase 1 measurement

Phase 1 (the hosted-only quick wins: `docker::test-pull`, the test-DB build fix,
read-only preview cache, `--no-cache` releases) ships first as its own PR, together with
#746 (backend `--parallel`, merged 2026-11-22). Before judging Phase 2, record for a
week after Phase 1 merges:

- Wall clock of `playwright.yml` runs (p50, p90).
- Critical path: the longest job's duration (p50, p90).
- Slot-minutes per run (sum of job durations).

`just ci::timing --runs 30 --workflows playwright.yml` collects these into
`.ci-timing/summary.md`. The baseline before this work: wall clock p50 17.5 / p90
22.4 min; longest job p50 16.6 / p90 21.7 min (last 39 successful runs).

## Human actions, in order

Nothing below can be done from a PR. Check each box when done.

1. **#746.** Already merged (2026-11-22, `fd1aa76d0`); nothing to coordinate. Re-measure
   the backend long pole as part of step 2.
2. **Phase 1 as its own PR.** Cut a branch at `b40a02aa86bd3148afd4d82c0ecf86deb8395205`
   (`ci(release): build release images without reading or writing the build cache`, the
   last Phase 1 commit on `ci/self-hosted-runners`), open it, merge it, and measure for
   a week as in [Phase 1 measurement](#phase-1-measurement).
3. **Confirm decision 1** below (is Phase 2 still wanted?). The other decisions keep
   their defaults unless you answer otherwise; the home runbook carries the same list.
4. **Tag ruleset.** Settings → Rules → Rulesets → New tag ruleset, target pattern
   `[0-9]*`, restrict creation, update and deletion, bypass list: the owner only.
   Release tags publish `draftforge/*`.
5. **H-R2.** Settings → Actions → General → Fork pull request workflows: "Require
   approval for all external contributors" (today `first_time_contributors`). Never
   approve a fork run whose diff touches `.github/`.
6. **H-R6.** Settings → Actions → General → Workflow permissions: "Read repository
   contents and packages permissions" (today `write`). Every workflow already declares
   `permissions` at workflow or job level (checked 2026-11-22 with
   `yq -e '.permissions != null or ([.jobs[] | select(.permissions == null)] | length == 0)'`
   over `.github/workflows/*.yml`; no workflow needs fixing first).
7. **H-R1b.** Repo Actions secret `ZOT_CI_PASSWORD`: the Zot `ci` password the home repo
   seeds into `zot-htpasswd.enc.yaml`. Without it `prepare` writes no Zot credential and
   builds still run, without the per-PR Zot cache.
8. **H-R7.** Repo variable `HOME_RUNNER_AUTHORS` (default `kettleofketchup`), equal to the
   home repo's `apps/github-runners/manifests/hooks/allowed-authors`.
9. **H-R3.** Repo variable `SELF_HOSTED_RUNNERS=true`, **only after** the home runbook's
   rollout checks pass and its canary (b) has shown the job-started hook refusing a
   job.
10. **H-R5.** After the first PR `prepare` pushes `draftforge-ci/*`: for each package,
    Package settings → Manage Actions access → add DraftForge with Read. Until then test
    jobs fail to pull, warn and fall back, so nothing breaks meanwhile.

### Decisions (spec section 7)

Each has a default that is built if nobody answers.

| # | Decision | Default | Answer |
|---|---|---|---|
| 1 | Is Phase 2 (the home build plane) still wanted after Phase 1 is measured? Its remaining value is lockfile and test-DB PRs only. | Build it, after Phase 1 merges and a week of measurement | [ ] |
| 2 | Who may use home runners? The four write collaborators are not on the list. | `kettleofketchup` only (matches `PREVIEW_AUTHORS`) | [ ] |
| 3 | May CI run on cp2, an etcd member? | cp2 only, required affinity, 2 runners × 1 CPU, etcd fsync alert as rollback trigger | [ ] |
| 4 | BuildKit cache on cp1's etcd disk | emptyDir on cp1, fsync alert as rollback trigger; a second disk is a hardware call | [ ] |
| 5 | Preview builds local or hosted? | Hosted, read-only GHCR `cache-from` | [ ] |
| 6 | Release builds `--no-cache`? | Yes | [ ] |
| 7 | GitHub settings H-R2 and H-R6 | Both required before H-R3 | [ ] |
| 8 | Alert receiver | None in this work; alerts visible in Alertmanager/Grafana only | [ ] |
| 9 | Migrations test split vs #746 | Drop the split, rely on #746's `--parallel` | [ ] |

The test-DB reuse stays enabled: the runner spike measured `just db::populate::fresh` at
22.8 s on 1 CPU, well under the 2-minute threshold that would have disabled it.

## Stopping

There are two different stops.

**Stop prepare.** Unset `SELF_HOSTED_RUNNERS` (or set it to anything but `true`), then
cancel queued `prepare` jobs in the Actions tab. Test jobs go back to today's path on
the next run. This does not stop the pool.

**Stop the pool.** Needed for anything that targets `runs-on: draftforge-home` from a
PR's own workflow file, which the variable does not gate. At once, out of band: suspend
the ARC GitHub App installation (Settings → GitHub Apps → Configure → Suspend) or remove
the `draftforge-home` runners in Settings → Actions → Runners. Then set `maxRunners: 0`
in the home repo through git. `kubectl scale` does not stick (ArgoCD self-heals), and
reverting the home merge orphans the workloads instead of removing them; see the home
runbook.

## Follow-ups (not in this work)

- Merging small Playwright jobs to cut fan-out: the only lever on burst queueing;
  recommended next.
- Chromium shard rebalancing.
- Path filters for shellcheck and changelog.
- GHCR cleanup of `draftforge-ci/*` older than 14 days.
- Zot Docker Hub credentials; a Talos node mirror to Zot.
- Rootless BuildKit; mTLS on BuildKit's port 1234.
- Image provenance attestations.
- A dashboard.
