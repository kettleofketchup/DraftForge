# CI Runners

Almost every CI job runs on GitHub-hosted runners. One job, `playwright.yml` `prepare`
(added in #787), builds the stack images and the test database once per content hash
before the test jobs start. It runs on `ubuntu-latest` by default. For pull requests from
allowlisted authors on branches in this repo, and only when a repository variable opts
in, it runs on a self-hosted runner in the home Kubernetes cluster (label
`draftforge-home`) instead.

The cluster side (ARC runners, BuildKit, Zot) lives in the home GitOps repo:
`apps/github-runners`, `apps/buildkit`, `apps/zot`, and the human runbook
`docs/runbooks/github-runners.md`. Merging there deploys.

!!! warning "The home runner is off until a human sets the repo variables"
    With `SELF_HOSTED_RUNNERS` unset, `prepare` runs on `ubuntu-latest` exactly as #787
    shipped it and `HOME_PREPARE` is `false`, so every job runs on hosted runners. See
    [Human actions](#human-actions-in-order).

## What runs where

| Job | Where | Reason |
|---|---|---|
| `playwright/prepare` | `ubuntu-latest`; the home runner for allowlisted same-repo PRs when `SELF_HOSTED_RUNNERS` is `true` | Builds missing stack images and the test DB once per hash; every test job waits for it |
| 15 stack jobs (chromium ×4, mobile ×2, herodraft ×2, layout, events ×2, org-features, backend ×3) and `unit` | GitHub | Execution-bound; the home cluster is far too small to run them |
| `preview-images/build` | GitHub | A 2-runner pool would saturate on every push and `npm run build` is uncached; it reads `main`'s GHCR `:buildcache` read-only instead |
| `preview-images/report` (`pull_request`), `preview-queue` (`pull_request_target`, `workflow_run`) | GitHub | Write permissions |
| `build-docker-images` | GitHub | Pushes prod `:latest` and GHCR `:buildcache`; trusted builds never touch the shared BuildKit |
| `build-test-db` | GitHub | No BuildKit benefit; daemon-only commands |
| `release-docker-images` | GitHub, `--no-cache` | Release artifacts |
| `record-demos`, changelog, shellcheck, format, shadcn-lint, docs, helm-chart, labelers | GitHub | Write permissions or too short to matter |

## The `prepare` job

There is one `prepare` job. Every Playwright and backend test job has `needs: prepare`
and `if: ${{ !cancelled() }}`: they start when `prepare` finishes, whether it succeeded,
failed or was skipped, and they keep their in-job fallbacks.

`just ci::prepare-images` probes GHCR with `docker buildx imagetools inspect` (no pull)
for `frontend-dev`, `backend-dev`, `playwright-runner`, `nginx` and `test-db` at their
content hashes, builds whatever is missing once, in parallel, and prints one line per
image (`present`, `built+pushed in Ns`, or why not). Failures are `::warning::`s and the
job still succeeds; the test jobs then build what is missing themselves. Timeout 30
minutes; permissions `contents: read`, `packages: write`.

What it builds with and where it pushes depends on the runner:

| | Hosted (`ubuntu-latest`, the default) | Home (`draftforge-home`, opt-in) |
|---|---|---|
| When | Every run, unless the home guard below holds | `SELF_HOSTED_RUNNERS == 'true'`, same-repo `pull_request`, PR author and triggering actor both in `HOME_RUNNER_AUTHORS` |
| Present means | `draftforge/<img>:<hash>` exists | `draftforge/<img>:<hash>` or this PR's `draftforge-ci/<img>:pr-<n>-<hash>` exists |
| Builder | Local `docker-container` buildx builder (`ci::buildx-builder`), only if something is missing | The home cluster's remote BuildKit (`ci::home-builder`), only if something is missing; Zot auth from `setup-builder` |
| Images pushed to | `draftforge/<img>:<hash>` only (`docker::buildx --hash-only`): never `:latest`, never a `:buildcache` export | `draftforge-ci/<img>:pr-<n>-<hash>` only (`docker::buildx --mode=pr`): never a `draftforge/` tag, never a GHCR cache export |
| Test DB | `docker::db::build` then `docker::db::push --hash-only` | `docker::db::build --mode=pr --pr=<n>` (populate on the runner, push through buildx); Python and Poetry are installed only when `ci::prepare-images --probe` reports `test-db` missing |
| Build cache | Reads GHCR `:buildcache` | Reads Zot `buildcache/pr/draftforge/<img>:pr-<n>` and GHCR `:buildcache`; writes only the Zot per-PR cache |
| Fork PRs | Read-only token: reports what is missing, builds nothing (`DF_PREPARE_READONLY`) | Never runs there |

The hosted column is #787 as merged; the only change on the hosted path is the
`runs-on` expression. On the home runner the step sets `DF_PREPARE_PR=<n>`, which turns
on PR mode. Without it, `ci::prepare-images` refuses to build on any runner whose
`RUNNER_ENVIRONMENT` is `self-hosted`, so a misrouted job cannot push PR code to
`draftforge/*`.

### How test jobs find the images

`setup-playwright-stack` starts the pulls in the background (`ci::prefetch-start`:
`docker::test-pull` and `docker::db::pull`). When `HOME_PREPARE` is `true` it first sets
`DF_CI_PR=<n>`, and each pull then tries, in order:

1. this PR's `draftforge-ci/<img>:pr-<n>-<hash>` (test DB: `draftforge-ci/test-db:pr-<n>-<hash>`),
   retagged locally as `draftforge/<img>:<hash>` and `:latest`, the names compose and
   the stale-image checks expect;
2. `draftforge/<img>:<hash>`, then `:latest`, as before;
3. the in-job rebuild of a missing or stale `frontend-dev`, `backend-dev` or
   `playwright-runner`, and the local `db::populate::fresh`.

With `HOME_PREPARE` `false` (every hosted `prepare` run) `DF_CI_PR` is unset and the
pulls are #787's.

## The kill switch and the allowlist

Two repository variables (Settings → Secrets and variables → Actions → Variables):

| Variable | Value | Effect |
|---|---|---|
| `SELF_HOSTED_RUNNERS` | `true` to enable; unset or anything else to disable | The kill switch. Unset means `prepare` runs on `ubuntu-latest` for every event. |
| `HOME_RUNNER_AUTHORS` | Comma-separated GitHub logins, default `kettleofketchup` | Who may use the home runner. Both the PR author and the triggering actor must be listed. |

`HOME_RUNNER_AUTHORS` must stay equal to the home repo's
`apps/github-runners/manifests/hooks/allowed-authors` (one login per line). The
runner's job-started hook reads that file and is authoritative: if the two differ, the
hook wins and refuses the job, and that run's `prepare` fails (test jobs then fall back
as in the failure table).

`prepare` picks its runner with this expression; the workflow-level `HOME_PREPARE` env
that test jobs read is the same guard, and `scripts/check-runs-on.sh` keeps the two
identical:

```yaml
runs-on: >-
  ${{ (vars.SELF_HOSTED_RUNNERS == 'true'
  && github.event_name == 'pull_request'
  && github.event.pull_request.head.repo.full_name == github.repository
  && contains(format(',{0},', vars.HOME_RUNNER_AUTHORS), format(',{0},', github.event.pull_request.user.login))
  && contains(format(',{0},', vars.HOME_RUNNER_AUTHORS), format(',{0},', github.triggering_actor)))
  && 'draftforge-home' || 'ubuntu-latest' }}
```

Bot authors and bot pushes onto a human PR fail the author or actor check (no bot is on
the allowlist). Forks fail the same-repo check. Pushes to `main`, tags and dispatches are
not `pull_request`, so they always run `prepare` hosted. #787's `vars.PREPARE_RUNNER`
switch is gone: it could send every event, fork PRs included, to whatever runner the
variable named.

### Failure behaviour, and the trade-off of waiting

Because test jobs `need` `prepare`, a home `prepare` that cannot start holds up the
whole run. That is the cost of adopting #787's single prepare job instead of an
optional job the tests never wait on, and it is accepted.

| Situation | Effect on the run |
|---|---|
| Kill switch off, or author not allowlisted | `prepare` runs hosted, as #787 |
| Home `prepare` fails, or the hook refuses it | Test jobs start at once (`!cancelled()`), pull what exists and rebuild the rest in-job |
| Home BuildKit unreachable | `ci::home-builder` errors, `prepare` fails, as the row above |
| Home `prepare` pushed but a test job cannot pull `draftforge-ci/*` (for example a package-permission error, see H-R5) | The pull falls back to `draftforge/<img>:<hash>`, then the in-job rebuild |
| Home pool busy (2 runners) | `prepare` waits for a runner; the test jobs wait with it |
| **`SELF_HOSTED_RUNNERS` is `true` and the home pool is down** (no runner carries `draftforge-home`: scale set not registered, controller down, cluster down) | GitHub does not fail the job: `prepare` stays queued, and every test job waits on it. GitHub cancels a job queued for 24 h, then the test jobs run (and fall back). The PR concurrency group (`cancel-in-progress` on `pull_request`) cancels the whole run on the next push, and the new run queues the same way. Fix: unset `SELF_HOSTED_RUNNERS`, then cancel or re-run the stuck runs; new runs go hosted at once |

Nothing about the home path can block `main`: pushes, tags and dispatches never match the
guard.

On lockfile PRs the home `prepare` uploads roughly 600 MB per dev image from the home
uplink. If that is slower than a hosted build, the home path costs wall clock on exactly
the PRs it was meant to speed up; canary (a) in the home runbook measures it.

## Cache and image names

| Name | Written by | Read by |
|---|---|---|
| `ghcr.io/kettleofketchup/draftforge/<img>:latest`, `:<version>` | Trusted hosted workflows and release tags | Everyone |
| `ghcr.io/kettleofketchup/draftforge/<img>:<hash>`, `draftforge/test-db:<hash>` | Trusted hosted workflows, release tags, and the **hosted** `prepare` job on any same-repo PR (`--hash-only`) | Everyone |
| `ghcr.io/kettleofketchup/draftforge/<img>:buildcache` | Trusted hosted builds only (`--mode=trusted --push` without `--hash-only`) | Trusted builds, preview builds, `prepare` (read-only) |
| `ghcr.io/kettleofketchup/draftforge-ci/<img>:pr-<n>-<hash>`, `draftforge-ci/test-db:pr-<n>-<hash>` | Home `prepare` only | That PR's test jobs (`DF_CI_PR`) and that PR's next home `prepare` |
| Zot `zot.zot.svc.cluster.local:5000/buildcache/pr/draftforge/<img>:pr-<n>` | Home `prepare`, with the `ci` credential | Home `prepare` (BuildKit only) |

Zot is plain HTTP on a ClusterIP. Only BuildKit talks to it; client-side tools
(`imagetools`, `docker login`, `docker pull`) assume HTTPS and must not target it.
`just ci::zot-auth` writes its credential straight into the docker client config, and
the buildx session forwards it to BuildKit.

**Trusted** means
`github.ref == 'refs/heads/main' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')`.
`build-docker-images` and `build-test-db` run only under that condition. Release tags
also publish `draftforge/*` (see below).

**Enforced:**

- No fork, bot, non-allowlisted author or non-PR event runs on a home runner (the
  job-started hook plus the fork approval policy, H-R2).
- Nothing built on the home cluster is pushed to `draftforge/*` or GHCR `:buildcache`
  (PR mode, plus `ci::prepare-images` refusing to build on a self-hosted runner outside
  PR mode), so nothing produced there is read by `main`, tags or releases.
- Dockerfile `RUN` steps cannot write Zot: anonymous access is read-only.
- Releases build with `--no-cache` and ignore `:buildcache`.

### Accepted by trust

These are known and not prevented:

- **Hosted `prepare` pushes PR-built `draftforge/<img>:<hash>` tags.** On a same-repo PR
  whose lockfile, Dockerfile or test-DB sources change, #787's hosted `prepare` builds
  the PR's code and pushes it under the content hash that `main` will later pull by tag
  existence. This is the owner's accepted choice for the hosted path (it never moves
  `:latest` or `:buildcache`). Only the home path is held to the stricter
  `draftforge-ci/*` split.
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
  commits to an allowlisted author's PR branch. The guard sends that push's `prepare`
  to `ubuntu-latest` (the triggering actor is not allowlisted), but those commits run on
  the home pool after the author's next push.
- **Same-repo writers can push to `draftforge/*` from a hosted PR job** by editing a
  workflow, as before #787. Default token permissions `read` (H-R6) narrows this, but a
  workflow can still request `packages: write`.
- **Tests on `main` pull `draftforge/*:<hash>` by tag existence.** Provenance
  attestations are a follow-up.

## `docker::buildx` modes

`just/docker/mod.just` `buildx` (called by every `docker::<svc>::build*` recipe) has two
explicit modes. Appending flags to one mode is not enough; the PR mode drops every
trusted tag.

| | `--mode=trusted` (default) | `--mode=pr --pr=<n>` |
|---|---|---|
| Used by | Hosted `main` and release workflows, hosted `prepare` (`--hash-only`), local builds | Home `prepare` only |
| Tags | `draftforge/<img>:latest`, `:<hash>` (plus `:<version>` with `--release`); `--hash-only`: `:<hash>` only | Only `draftforge-ci/<img>:pr-<n>-<hash>` |
| Cache from | GHCR `:buildcache` (none with `--no-cache`) | Zot `buildcache/pr/draftforge/<img>:pr-<n>`, then GHCR `:buildcache` |
| Cache to | GHCR `:buildcache` with `--push` (none with `--no-cache` or `--hash-only`) | Zot per-PR cache only, `ignore-error=true` |
| Output | `--push`, or `--load` | Always `--push`, never `--load` |
| Rejects | `--pr`; `--hash-only` with `--release` | `--release`, `--no-cache`, `--hash-only` |

Both add `--platform linux/amd64`, and `--provenance=false` (trusted mode skips it under
podman, whose buildx shim rejects it). `docker::db::build --mode=pr --pr=<n>` builds the
busybox test-DB image through buildx and pushes only
`draftforge-ci/test-db:pr-<n>-<hash>`, with no daemon commands. The recipe tests in
`scripts/slot_tests/test_docker_recipes.py` and `test_ci_prepare_images.py` stub
`docker` and assert that PR mode emits no `draftforge/` tag, no `:latest` and no GHCR
`cache-to`.

## The `runs-on` guard is not a security control

`scripts/check-runs-on.sh` (`just ci::check-runs-on`, the `runs-on-guard` job in
`shellcheck.yml`) fails when:

- any job's `runs-on` is not a literal GitHub-hosted label (`ubuntu-*`, `windows-*`,
  `macos-*`), except `playwright.yml` `prepare`. An expression, a variable such as
  `fromJSON(vars.PREPARE_RUNNER)`, `self-hosted`, a runner group or a matrix value can
  all land a job on a self-hosted runner, so none is allowed;
- `prepare`'s `runs-on` is not exactly the guarded expression above (whitespace
  aside; containing the clauses is not enough, `(... || true)` would pass that), or it
  has no `timeout-minutes`;
- `env.HOME_PREPARE` is not exactly the same guard;
- `draftforge-home` appears anywhere other than `prepare`'s `runs-on`;
- a job calls a reusable workflow from another repository;
- a workflow that can use the label triggers on `pull_request_target` or `workflow_run`.

So no job can resolve to a self-hosted label without the guard, and the one
`pull_request_target` workflow (`preview-queue.yml`) stays on `ubuntu-latest`.

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
2. **Phase 1 as its own PR.** Cut a branch at the commit
   `ci(release): build release images without reading or writing the build cache`, the
   last Phase 1 commit on `ci/self-hosted-runners` (its SHA changes whenever the branch
   is rebased; `git log --grep 'build release images without'`), open it, merge it, and
   measure for a week as in [Phase 1 measurement](#phase-1-measurement).
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
   job. From then on every allowlisted same-repo PR's test jobs wait for a home runner:
   if the pool is down, unset the variable (see [Stopping](#stopping)).
10. **H-R5.** After the first home `prepare` pushes `draftforge-ci/*`: for each package,
    Package settings → Manage Actions access → add DraftForge with Read. Until then test
    jobs fail to pull it, fall back to `draftforge/<img>:<hash>` or rebuild in-job, so
    nothing breaks meanwhile.

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

**Stop home prepare.** Unset `SELF_HOSTED_RUNNERS` (or set it to anything but `true`).
New runs send `prepare` to `ubuntu-latest` at once. Runs already queued on
`draftforge-home` keep waiting (their `runs-on` was evaluated when they were queued), and
their test jobs wait with them: cancel those runs in the Actions tab and re-run them, or
push again (PR concurrency cancels the old run). This does not stop the pool.

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
