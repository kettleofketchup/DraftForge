# DraftForge Helm chart

This chart deploys DraftForge on Kubernetes: the backend (Daphne), the frontend (SSR), the
celery worker, celery beat, the Discord bot and redis. It is used today for per-PR preview
environments. Its defaults are prod-shaped for a future `dota.kettle.sh` cutover.

ArgoCD renders this directory straight from a pinned commit. Read the render-safety contract
below before you change anything under `helm/`.

## Profiles

| Profile | Values | What renders |
|---|---|---|
| **default** (prod-shaped) | `values.yaml` | The application only. Backend data is on a PVC (cluster default StorageClass) and the backend uses a `Recreate` strategy. Celery beat and the Discord bot are on. An IngressRoute is rendered for `dota.kettle.sh`. No Namespace, quota, LimitRange or NetworkPolicy. |
| **preview** | `values.yaml` + `values-preview.yaml` (`preview.enabled: true`) + the deploying ApplicationSet's `valuesObject` | Also renders the namespace controls at sync-wave `-1`: the Namespace with PSA `restricted`, a ResourceQuota, a LimitRange and four NetworkPolicies, plus a rate-limit Middleware ahead of forward-auth. SQLite is on an `emptyDir`, data is seeded, beat and the bot are off, rollouts use `maxSurge 1 / maxUnavailable 0`, and `progressDeadlineSeconds` is 1500 everywhere. A guard fails the render unless the security-relevant values are present, and also fails any `draftforge-pr-*` namespace rendered without `preview.enabled`. |

`values-preview.yaml` holds only the non-security preview settings. The ApplicationSet sets
everything per-preview or security-relevant (image, host, namespace controls, forward-auth),
and its values take precedence. The deploying cluster owns every preview limit: the
ResourceQuota, the LimitRange and the rate limit all come from its `valuesObject`; the chart
only requires that they are set. `tests/fixtures/preview-appset-values.yaml` is an example
`valuesObject` with placeholder names for release namespace `draftforge-pr-1`.

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
| `priorityClassName` | `""` | Required in preview mode. |
| `previewCommit` | `""` | When set, becomes the pod-template annotation `draftforge.kettle.sh/commit` on every app Deployment (not redis). The ArgoCD notification triggers key on it. |
| `backend.replicas` | `1` | The schema allows only 1 (single SQLite writer). |
| `backend.progressDeadlineSeconds` | `900` | Previews: 1500. |
| `frontend.progressDeadlineSeconds` | `300` | Previews: 1500. |
| `celeryWorker.enabled` / `.concurrency` | `true` / `20` | Previews: concurrency 4, deadline 1500. |
| `celeryBeat.enabled` | `true` | Previews: `false`. With no credentials it would poll Discord and Steam every 30-60s. |
| `discordBot.enabled` | `true` | Previews: `false`. |
| `redis.enabled` / `.image` / `.dataSizeLimit` | `true` / `redis:8.2.1-alpine` / `256Mi` | `emptyDir` capped at `dataSizeLimit`, no persistence, `Recreate`, and no checksum or commit annotation, so app commits do not restart it. |
| `<component>.resources` | see `values.yaml` | Every enabled container must set `cpu`, `memory` and `ephemeral-storage` requests and limits, or the render fails. |
| `persistence.enabled` / `.size` / `.storageClass` / `.accessMode` | `true` / `2Gi` / `""` (cluster default) / `ReadWriteOnce` | Previews: `false`, which gives an `emptyDir` with a 1Gi limit. Must be `false` in preview mode. |
| `migrations.enabled` | `true` | Runs the `migrate` init container. |
| `seed.enabled` / `.commands` | `false` / `["populate_all --force"]` | Previews: `true`. |
| `env.*` | `nodeEnv: production`, `debug/test/release/ci: false`, `siteUrl: ""`, `otelEnabled: false`, `logFormat: json`, `logLevel: INFO`, `extra: {}` | Populates ConfigMap `draftforge-env`. `siteUrl` defaults to `https://<ingress.host>`. |
| `secrets.create` / `.djangoSecretKey` / `.internalServiceToken` | `false` / `""` / `""` | Previews create the Secret with dummy values. Prod uses `extraEnvSecrets`. |
| `extraEnvSecrets` | `[]` | Extra Secrets loaded with `envFrom` (prod). Previews leave this empty. |
| `ingress.enabled` / `.host` / `.entryPoint` | `true` / `dota.kettle.sh` / `websecure` | Previews: the host must be `<namespace>.<preview.hostSuffix>`. |
| `ingress.tls.secretName` | `""` | The `tls` key is emitted only when this is set. |
| `ingress.authentik.enabled` / `.middlewareName` / `.middlewareNamespace` | `false` / `""` / `""` | The forward-auth middleware, listed on every route after the rate limit. All three are required in preview mode. |
| `ingress.blockInternalApi` | `true` | Denies `/api/internal` from outside (see below). Required in preview mode. |
| `ingress.stripIdentityHeaders` | `false` | Removes the `ingress.identityHeaders` headers before they reach the app. Required in preview mode. |
| `ingress.identityHeaders` | the `X-authentik-*` identity headers | Must cover the forward-auth middleware's `authResponseHeaders`. Must be non-empty in preview mode. |
| `ingress.rateLimit.{enabled,average,burst,period,sourceHeader}` | `false` / `0` / `0` / `1s` / `""` | Traefik `rateLimit`, the first middleware on every route. `sourceHeader` names the client-IP header set by a proxy in front of Traefik; empty uses the remote address. Preview mode requires `enabled` and positive `average` and `burst`. |
| `preview.enabled` | `false` | `values-preview.yaml` sets `true`. A `draftforge-pr-*` namespace fails to render without it, and `env.test` is allowed only with it. |
| `preview.hostSuffix` | `""` | For example `preview.example.test`. |
| `preview.resourceQuota.hard` | `{}` | The ResourceQuota `spec.hard`. Preview mode requires `pods`, `requests.cpu`, `requests.memory`, `requests.ephemeral-storage`, `limits.cpu`, `limits.memory`, `limits.ephemeral-storage`, `services`, `secrets`, `configmaps` and `count/deployments.apps`; any other quota key may be added. The chart pins PVCs, `requests.storage`, LoadBalancer and NodePort Services, Jobs and CronJobs at `0` and fails a render that sets them to anything else. The budget check compares the rendered pods, rollout surge included, with this quota. |
| `preview.limitRange.{default,defaultRequest,max}` | `{}` | The Container LimitRange. Each needs `cpu`, `memory` and `ephemeral-storage` in preview mode. The budget check fails when a chart container exceeds `max`. |
| `preview.networkPolicy.ingressNamespace` | `""` | The namespace Traefik runs in. Required in preview mode. |
| `podSecurityContext` | `fsGroup/runAsUser/runAsGroup: 1000`, `runAsNonRoot`, `RuntimeDefault` | Every container is PSA-`restricted` compliant. |

`values.schema.json` checks types, and the `preview` objects and `ingress.rateLimit` are closed, so a misspelled key fails `helm lint` instead of being ignored.

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

`scripts/helm_render_safety.sh helm` and the helm-unittest suites enforce these rules. A
deploying repo that pins the chart should re-check them at the commit it pins.

## Versioning and the chart tag

- `version` in `Chart.yaml` is chart semver. Bump it by hand in the same PR as any change
  under `helm/` that reaches the rendered chart. CI fails a PR that changes `helm/` without a
  bump (`scripts/helm_version_bump_check.sh`); changes only to `helm/tests/` or
  `helm/README.md` are exempt.
- `appVersion` is informational. Edit it by hand together with a `version` bump. The app
  release tooling never touches `helm/`, and a guard test keeps it that way.
- After the PR merges, the owner tags **the merge commit** `chart-v<version>`. The tag must be
  annotated (`git tag -a`) and must not be a lightweight tag. Deployers pin the commit SHA
  behind that tag, never the tag name. Never move an existing chart tag.

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

Render and test with **Helm v3.19.4**, the Helm version bundled in the ArgoCD repo-server
that renders the chart, so local and CI renders match what ArgoCD deploys. The `helm` on your
`PATH` may be Helm 4. The just recipes run the mise-managed v3.19.4
(the `helm` binary under `mise where helm@3.19.4`, unless `HELM` is set). CI installs it with `azure/setup-helm`. When the
repo-server's bundled Helm changes, update the pins in `just/helm.just` and
`.github/workflows/helm-chart.yml` together.

```sh
just helm::plugins            # install the pinned helm-unittest into Helm v3.19.4
just helm::lint               # lint --strict, default and preview profiles
just helm::template preview   # render a profile to stdout
just helm::test               # unittest, budget, render-safety, kubeconform, script tests
```

## Operating previews

The DraftForge side of the preview queue is controlled from this repo:

- `PREVIEW_CAP` (repo variable, 0 to 3) is the number of preview slots. `0` pauses previews.
  The next queue run trims holders to the cap and keeps the longest-standing ones.
- The `no-preview` label opts a PR out. Removing `preview-env` by hand does not last; the
  queue adds it back.
- Idle or failed holders are evicted while someone waits (`PREVIEW_IDLE_DAYS`, default 7).
- If the queue is not moving, run `preview-queue` with `workflow_dispatch`, and re-enable the
  cron in the Actions tab if GitHub disabled it after 60 days of inactivity.

Everything on the cluster side (the ApplicationSet, the preview limits, DNS, notifications
and its runbook) lives with the deploying cluster's GitOps config, not in this repo.

## Preview isolation notes

Previews run PR-built code behind forward-auth. Two limits of that model:

- `ingress.identityHeaders` must cover every header the forward-auth middleware returns
  (`authResponseHeaders`), or PR code receives it. The deploying cluster sets the list and
  should check it against the middleware.
- A preview host that shares a registrable domain with other internal apps is same-site with
  them, so their `SameSite=Lax` cookies reach PR code, and so does the forward-auth session
  cookie. Previews are therefore limited to the repo owner's PRs; serve them from a separate
  registrable domain before widening that.
