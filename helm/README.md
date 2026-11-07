# DraftForge Helm chart

This chart deploys DraftForge on Kubernetes: the backend (Daphne), the frontend (SSR), the
celery worker, celery beat, the Discord bot and redis. It is used today for per-PR preview
environments on the home cluster. Its defaults are prod-shaped for a future `dota.kettle.sh`
cutover.

ArgoCD renders this directory straight from a pinned commit. Read the render-safety contract
below before you change anything under `helm/`.

## Profiles

| Profile | Values | What renders |
|---|---|---|
| **default** (prod-shaped) | `values.yaml` | The application only. Backend data is on a PVC (`ceph-block`) and the backend uses a `Recreate` strategy. Celery beat and the Discord bot are on. An IngressRoute is rendered for `dota.kettle.sh`. No Namespace, quota, LimitRange or NetworkPolicy. |
| **preview** | `values.yaml` + `values-preview.yaml` + the home ApplicationSet's `valuesObject` (`preview.enabled: true`) | Also renders the namespace controls at sync-wave `-1`: the Namespace with PSA `restricted`, a ResourceQuota, a LimitRange and four NetworkPolicies. SQLite is on an `emptyDir`, data is seeded, beat and the bot are off, rollouts use `maxSurge 1 / maxUnavailable 0`, and `progressDeadlineSeconds` is 1500 everywhere. A guard fails the render unless the security-relevant values are present. |

`values-preview.yaml` holds only the non-security preview settings. The ApplicationSet sets
everything per-preview or security-relevant (image, host, namespace controls, forward-auth),
and its values take precedence. `tests/fixtures/preview-appset-values.yaml` is a literal copy
of that `valuesObject` for release namespace `draftforge-pr-1`.

Render either profile locally with `just helm::template default` or
`just helm::template preview`.

## Values

| Key | Default | Notes |
|---|---|---|
| `fullnameOverride` | `""` | Name prefix for non-Service resources. Defaults to `draftforge`, never the release name. |
| `image.registry` | `ghcr.io/kettleofketchup/draftforge` | Images are `<registry>/backend:<tag>` and `<registry>/frontend:<tag>`. Previews use `ghcr.io/kettleofketchup/draftforge-preview`. |
| `image.tag` | `""` | Defaults to `appVersion`. Previews set `pr-<n>-<sha7>`. A prod cutover sets it explicitly. |
| `image.pullPolicy` | `IfNotPresent` | |
| `image.pullSecrets` | `[]` | Previews leave this empty. |
| `priorityClassName` | `""` | Previews get `preview-low`. Required in preview mode. |
| `previewCommit` | `""` | When set, becomes the pod-template annotation `draftforge.kettle.sh/commit` on every Deployment. The ArgoCD notification triggers key on it. |
| `backend.replicas` | `1` | The schema allows only 1 (single SQLite writer). |
| `backend.progressDeadlineSeconds` | `900` | Previews: 1500. |
| `frontend.progressDeadlineSeconds` | `300` | Previews: 1500. |
| `celeryWorker.enabled` / `.concurrency` | `true` / `20` | Previews: concurrency 4, deadline 1500. |
| `celeryBeat.enabled` | `true` | Previews: `false`. With no credentials it would poll Discord and Steam every 30-60s. |
| `discordBot.enabled` | `true` | Previews: `false`. |
| `redis.enabled` / `.image` | `true` / `redis:8.2.1-alpine` | `emptyDir`, no persistence, `Recreate`. |
| `<component>.resources` | see `values.yaml` | Every enabled container must set `requests.cpu`, `requests.memory` and `limits.memory`, or the render fails. |
| `persistence.enabled` / `.size` / `.storageClass` / `.accessMode` | `true` / `2Gi` / `ceph-block` / `ReadWriteOnce` | Previews: `false`, which gives an `emptyDir` with a 1Gi limit. Must be `false` in preview mode. |
| `migrations.enabled` | `true` | Runs the `migrate` init container. |
| `seed.enabled` / `.commands` | `false` / `["populate_all --force"]` | Previews: `true`. |
| `env.*` | `nodeEnv: production`, `debug/test/release/ci: false`, `siteUrl: ""`, `otelEnabled: false`, `logFormat: json`, `logLevel: INFO`, `extra: {}` | Populates ConfigMap `draftforge-env`. `siteUrl` defaults to `https://<ingress.host>`. |
| `secrets.create` / `.djangoSecretKey` / `.internalServiceToken` | `false` / `""` / `""` | Previews create the Secret with dummy values. Prod uses `extraEnvSecrets`. |
| `extraEnvSecrets` | `[]` | Extra Secrets loaded with `envFrom` (prod). Previews leave this empty. |
| `ingress.enabled` / `.host` / `.entryPoint` | `true` / `dota.kettle.sh` / `websecure` | Previews: the host must be `<namespace>.<preview.hostSuffix>`. |
| `ingress.tls.secretName` | `""` | The `tls` key is emitted only when this is set. Previews: `home-kettle-sh-tls`. |
| `ingress.authentik.enabled` / `.middlewareName` / `.middlewareNamespace` | `false` / `authentik-forwardauth` / `authentik` | When enabled, it is the first middleware on every route. Required in preview mode. |
| `ingress.blockInternalApi` | `true` | Denies `/api/internal` from outside (see below). Required in preview mode. |
| `ingress.stripIdentityHeaders` | `false` | Blanks the five `X-authentik-*` identity headers before they reach the app. Required in preview mode. |
| `preview.enabled` | `false` | `true` only from the home ApplicationSet. |
| `preview.hostSuffix` | `""` | For example `home.kettle.sh`. |
| `preview.quota.{pods,requestsCpu,requestsMemory,limitsMemory}` | `""` | All are required in preview mode. The budget check compares the rendered pods against this quota. |
| `preview.networkPolicy.ingressNamespace` | `""` | The namespace Traefik runs in. Required in preview mode. |
| `podSecurityContext` | `fsGroup/runAsUser/runAsGroup: 1000`, `runAsNonRoot`, `RuntimeDefault` | Every container is PSA-`restricted` compliant. |

`values.schema.json` checks types, so a typo fails `helm lint`.

## One release per namespace

The Services are named exactly `backend`, `frontend` and `redis`, not release-prefixed. The
app's hardcoded defaults expect these names: `SSR_API_URL`, `INTERNAL_API_URL`, celery
`REDIS_HOST`, and `"backend"` in `ALLOWED_HOSTS`. Install at most one release of this chart
per namespace.

## Render-safety contract

ArgoCD renders `helm/` directly at the pinned commit, so the chart must stay plain Helm:

- no `dependencies:` in `Chart.yaml` and no `charts/` directory, because the repo-server would
  fetch arbitrary URLs;
- no `.argocd-source*.yaml`, `kustomization.y*ml` or `Kustomization` file under `helm/`, and
  no symlinks;
- no `.gitmodules` and no gitlink (mode 160000) anywhere in the repository, because the
  repo-server runs submodule update for the whole checkout;
- no `helm.sh/hook`, `argocd.argoproj.io/hook` or `argocd.argoproj.io/sync-options`
  annotation;
- `previewCommit` keeps producing the `draftforge.kettle.sh/commit` pod annotation.

`scripts/helm_render_safety.sh helm` and the helm-unittest suites enforce these rules. The home
repo's pin check re-checks them at the exact commit it pins, with its own copy of the checks.

## Versioning and the chart tag

- `version` in `Chart.yaml` is chart semver. Bump it by hand in the same PR as any change
  under `helm/`. CI fails a PR that changes `helm/` without a bump
  (`scripts/helm_version_bump_check.sh`).
- `appVersion` is informational. Edit it by hand together with a `version` bump. The app
  release tooling never touches `helm/`, and a guard test keeps it that way.
- After the PR merges, the owner tags **the merge commit** `chart-v<version>`. The tag must be
  annotated (`git tag -a`) and must not be a lightweight tag. The home repo pins the commit
  SHA behind that tag, never the tag name. Never move an existing chart tag; the pin script
  refuses a retagged name.

## Chart/image compatibility

A pin bump re-renders every live preview with the new chart. Each preview still runs images
built from its own PR's base. So a chart change must keep working with images built from any
DraftForge `main` commit since the previous chart tag. That rules out a new required env var,
management command, probe path or entrypoint assumption that older images lack. If the chart
needs new app code, ship it in two steps: the app change first, then the chart change once
older preview PRs have rebased or closed. Reviewers of a `helm/` PR check this. A preview
broken by a violation shows up as `degraded`.

There is also a preview compatibility floor. The `preview-images` workflow builds images only
for a branch that has preview support: `backend/backend/env_utils.py` exists and
`frontend/Dockerfile` declares `ARG VITE_PREVIEW_TEST_FEATURES`. An older branch gets a comment
asking for a rebase on `main`, and no images are built.

## `/api/internal` and a prod cutover

With `ingress.blockInternalApi: true` (the default, and mandatory in preview mode), the
IngressRoute sends `/api/internal` to an `ipAllowList` of `127.0.0.1/32`, so every external
request gets 403. Prod nginx does not do this; it proxies all of `/api`. The block is needed
behind Traefik because `INTERNAL_SERVICE_ALLOWED_IPS` includes `10.0.0.0/8` by default, and
Traefik's pod IPs are in that range. A prod cutover must keep this behaviour change or turn it
off deliberately.

## Helm version

Render and test with **Helm v3.19.4**. That is the Helm bundled in the ArgoCD v3.3.4
repo-server, so local and CI renders match what ArgoCD deploys. The `helm` on your `PATH` may be
Helm 4. The just recipes use the mise-installed v3.19.4
(`export HELM="$(mise where helm@3.19.4)/linux-amd64/helm"`). CI installs it with
`azure/setup-helm`. When ArgoCD is upgraded, re-check the repo-server's bundled Helm and
update the pins in `just/helm.just` and `.github/workflows/helm-chart.yml` together.

```sh
just helm::plugins            # install the pinned helm-unittest into Helm v3.19.4
just helm::lint               # lint --strict, default and preview profiles
just helm::template preview   # render a profile to stdout
just helm::test               # unittest, budget, render-safety, kubeconform, script tests
```

## Runbook (owner break-glass only)

Agents must not perform these steps. They are for the owner only. Every kubectl command is
read-only and passes `--context admin@KettleCluster`.

- **Retry exhausted / App stuck OutOfSync:** push a new commit, or
  `ARGOCD_NAMESPACE=argocd argocd app terminate-op draftforge-pr-<n> --core` then
  `argocd app sync draftforge-pr-<n> --core`.
- **App stuck deleting with an operation in flight:** `argocd app terminate-op ... --core`.
- **Namespace stuck Terminating:** first run
  `kubectl get ns <ns> -o jsonpath='{.status.conditions}'` and
  `kubectl get apiservice | grep False`. An unavailable aggregated API (for example
  `metrics-server`) blocks namespace deletion until it is healthy again. After a force-delete,
  inspect the remaining finalizers and remove them as a sanctioned break-glass step.
- **Queue not moving:** run `preview-queue` with `workflow_dispatch`. If GitHub disabled the
  cron after 60 days of inactivity, re-enable it in the Actions tab. Check the `preview-queue`
  status on the waiting PR's head.
- **Capacity short:** lower the repo variable `PREVIEW_CAP`. The next queue run trims holders
  to the cap and keeps the longest-standing ones. `PREVIEW_CAP=0` pauses previews entirely.
- **Opting a PR out:** add the `no-preview` label. Removing `preview-env` by hand does not
  last; the queue adds it back.
- **Queue stuck behind idle PRs:** idle or failed holders are evicted automatically while
  someone waits (`PREVIEW_IDLE_DAYS`, default 7).
- **DNS reconciler failing:** check the token (expiry, permissions) and the CronJob logs. The
  reconciler fixes leftovers on its next good run.
- **Token rotation:** run `scripts/draftforge-preview-secrets.sh --only <token>` (home repo)
  before the token expires. The comment token is re-set inside
  `notifications-secrets.enc.yaml`, never in a new file.
- **Merge-conflicted PR stuck at "Waiting for preview images" or failed:** resolve the
  conflict and push. A head that never got a `preview-images` run (pushed before the workflow
  reached `main`, or skipped) needs a push or a close-and-reopen.
- **Rollback**, from smallest to largest scope, each verified read-only:
  1. Pause: set `PREVIEW_CAP=0` and wait one queue run.
     `kubectl --context admin@KettleCluster -n argocd get applications -o name | grep draftforge-pr-`
     prints nothing once the generator polls.
  2. Remove previews: a revert commit that unregisters `draftforge-previews.yaml` from the home
     repo's `argocd-apps/kustomization.yaml`. Deleting the ApplicationSet cascades to every
     preview App and namespace (there is no `preserveResourcesOnDeletion`).
  3. Back out notifications and metrics: `git revert` the commit that changed the argo-cd
     `valuesObject`.
  4. Stop DNS: remove the CronJob in Git. Any `draftforge-pr-*` CNAMEs left behind then need a
     manual Cloudflare cleanup.
  5. DraftForge: revert the settings and frontend commits. They preserve defaults, so a revert
     is safe.
- **Chart update:** a DraftForge PR changes `helm/` and bumps `version`. The owner runs the
  home pin script with `--chart-dir` on the PR head. The PR is reviewed and merged. The owner
  tags the merge commit `chart-vX.Y.Z` (annotated) and pushes the tag, then runs the pin script
  in a home branch and reviews the printed `helm/` diff. Merge the home PR once home CI is
  green and the owner-run ksops builds pass. Never hand-edit the SHA.
