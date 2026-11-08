{{/*
Preview-mode guard rails. Fails the render when:
- the release namespace looks like a preview (draftforge-pr-*) but preview.enabled
  is false, so a valuesObject that drops the flag cannot render an unguarded app;
- env.test is true outside preview mode, because TEST exposes the test-login
  endpoints;
- env.extra names a key the chart manages: TEST, DEBUG, CI and NODE_ENV set
  there would turn the test-login endpoints on around the env.test check, and
  in preview mode SQLITE_PATH, REDIS_HOST or the host keys would change;
- outside preview mode, neither secrets.create nor extraEnvSecrets is set, so
  DJANGO_SECRET_KEY would be unset and the backend would fall back to the
  development key that is public in this repository;
- preview.enabled is true and any security-relevant value the deploying
  ApplicationSet must set is missing.
It protects against a misconfigured ApplicationSet, not against the chart itself.
Included first in every template, so no template renders without it.
Emits nothing. Takes the root context.
*/}}
{{- define "draftforge.previewGuard" -}}
{{- $v := .Values -}}
{{- $ns := .Release.Namespace -}}
{{- if and (hasPrefix "draftforge-pr-" $ns) (not $v.preview.enabled) -}}
{{- fail (printf "draftforge preview guard: release namespace %q is a preview namespace, so preview.enabled must be true" $ns) -}}
{{- end -}}
{{- if and $v.env.test (not $v.preview.enabled) -}}
{{- fail "draftforge preview guard: env.test exposes the test-login endpoints and is allowed only with preview.enabled" -}}
{{- end -}}
{{- $chartEnv := include "draftforge.envChartData" . | fromYaml -}}
{{- range $k := keys ($v.env.extra | default dict) | sortAlpha -}}
{{- if hasKey $chartEnv $k -}}
{{- fail (printf "draftforge guard: env.extra must not set the chart-managed key %q; use the matching env.* value" $k) -}}
{{- end -}}
{{- end -}}
{{- if and (not $v.preview.enabled) (not $v.secrets.create) (not $v.extraEnvSecrets) -}}
{{- fail "draftforge guard: set secrets.create or extraEnvSecrets (with DJANGO_SECRET_KEY); without one the backend uses the public development secret key" -}}
{{- end -}}
{{- if $v.preview.enabled -}}
{{- if not (regexMatch "^draftforge-pr-[0-9]+$" $ns) -}}
{{- fail (printf "draftforge preview guard: release namespace %q must match ^draftforge-pr-[0-9]+$" $ns) -}}
{{- end -}}
{{- if not $v.ingress.enabled -}}
{{- fail "draftforge preview guard: ingress.enabled must be true" -}}
{{- end -}}
{{- if not $v.ingress.authentik.enabled -}}
{{- fail "draftforge preview guard: ingress.authentik.enabled must be true" -}}
{{- end -}}
{{- if not $v.ingress.authentik.middlewareName -}}
{{- fail "draftforge preview guard: ingress.authentik.middlewareName must be set" -}}
{{- end -}}
{{- if not $v.ingress.authentik.middlewareNamespace -}}
{{- fail "draftforge preview guard: ingress.authentik.middlewareNamespace must be set" -}}
{{- end -}}
{{- /* Checked on its own: an empty suffix would compare the host against "<namespace>." */ -}}
{{- if not $v.preview.hostSuffix -}}
{{- fail "draftforge preview guard: preview.hostSuffix must be set" -}}
{{- end -}}
{{- $wantHost := printf "%s.%s" $ns $v.preview.hostSuffix -}}
{{- if ne (toString $v.ingress.host) $wantHost -}}
{{- fail (printf "draftforge preview guard: ingress.host must be %q, got %q" $wantHost (toString $v.ingress.host)) -}}
{{- end -}}
{{- if not $v.ingress.blockInternalApi -}}
{{- fail "draftforge preview guard: ingress.blockInternalApi must be true" -}}
{{- end -}}
{{- if not $v.ingress.stripIdentityHeaders -}}
{{- fail "draftforge preview guard: ingress.stripIdentityHeaders must be true" -}}
{{- end -}}
{{- if not $v.ingress.identityHeaders -}}
{{- fail "draftforge preview guard: ingress.identityHeaders must list the forward-auth identity headers" -}}
{{- end -}}
{{- $rl := $v.ingress.rateLimit -}}
{{- if not $rl.enabled -}}
{{- fail "draftforge preview guard: ingress.rateLimit.enabled must be true" -}}
{{- end -}}
{{- range $key := list "average" "burst" -}}
{{- if le (int (index $rl $key)) 0 -}}
{{- fail (printf "draftforge preview guard: ingress.rateLimit.%s must be greater than 0" $key) -}}
{{- end -}}
{{- if le (int (index ($rl.aggregate | default dict) $key | default 0)) 0 -}}
{{- fail (printf "draftforge preview guard: ingress.rateLimit.aggregate.%s must be greater than 0" $key) -}}
{{- end -}}
{{- end -}}
{{- if $v.persistence.enabled -}}
{{- fail "draftforge preview guard: persistence.enabled must be false" -}}
{{- end -}}
{{- if not $v.priorityClassName -}}
{{- fail "draftforge preview guard: priorityClassName must be set" -}}
{{- end -}}
{{- if not $v.preview.networkPolicy.ingressNamespace -}}
{{- fail "draftforge preview guard: preview.networkPolicy.ingressNamespace must be set" -}}
{{- end -}}
{{- $hard := $v.preview.resourceQuota.hard | default dict -}}
{{- range $key := include "draftforge.quotaRequiredKeys" . | splitList " " -}}
{{- if eq (toString (index $hard $key | default "")) "" -}}
{{- fail (printf "draftforge preview guard: preview.resourceQuota.hard[%q] must be set" $key) -}}
{{- end -}}
{{- end -}}
{{- range $key, $want := include "draftforge.quotaPinned" . | fromYaml -}}
{{- if and (hasKey $hard $key) (ne (toString (index $hard $key)) $want) -}}
{{- fail (printf "draftforge preview guard: preview.resourceQuota.hard[%q] is fixed at %q by the chart" $key $want) -}}
{{- end -}}
{{- end -}}
{{- range $section := list "default" "defaultRequest" "max" -}}
{{- $limits := index $v.preview.limitRange $section | default dict -}}
{{- range $res := list "cpu" "memory" "ephemeral-storage" -}}
{{- if eq (toString (index $limits $res | default "")) "" -}}
{{- fail (printf "draftforge preview guard: preview.limitRange.%s[%q] must be set" $section $res) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* ResourceQuota keys the deploying cluster must set, space-separated. */}}
{{- define "draftforge.quotaRequiredKeys" -}}
pods requests.cpu requests.memory requests.ephemeral-storage limits.cpu limits.memory limits.ephemeral-storage services secrets configmaps count/deployments.apps
{{- end -}}

{{/*
ResourceQuota keys the chart fixes at 0, as YAML: a preview gets no storage, no
externally reachable Service and no Job or CronJob.
*/}}
{{- define "draftforge.quotaPinned" -}}
count/persistentvolumeclaims: "0"
requests.storage: "0"
services.loadbalancers: "0"
services.nodeports: "0"
count/jobs.batch: "0"
count/cronjobs.batch: "0"
{{- end -}}
