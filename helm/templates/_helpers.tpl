{{/*
Resource name prefix. fullnameOverride, or the constant "draftforge". It is
never derived from the release name: one release per namespace, and Services
are the fixed names backend, frontend and redis.
*/}}
{{- define "draftforge.fullname" -}}
{{- default "draftforge" .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common metadata labels. Takes the root context. */}}
{{- define "draftforge.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: draftforge
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels for one component. Emits exactly these two keys; the
NetworkPolicies select on app.kubernetes.io/component.
Usage: include "draftforge.selectorLabels" (dict "root" $ "component" "backend")
*/}}
{{- define "draftforge.selectorLabels" -}}
app.kubernetes.io/name: draftforge
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* Image tag: image.tag, or the chart appVersion. Takes the root context. */}}
{{- define "draftforge.imageTag" -}}
{{- .Values.image.tag | default .Chart.AppVersion -}}
{{- end -}}

{{/*
Full image reference <image.registry>/<img>:<tag>.
Usage: include "draftforge.image" (dict "root" $ "img" "backend")
*/}}
{{- define "draftforge.image" -}}
{{- printf "%s/%s:%s" .root.Values.image.registry .img (include "draftforge.imageTag" .root) -}}
{{- end -}}

{{/* Pod-level securityContext from podSecurityContext. Takes the root context. */}}
{{- define "draftforge.podSecurity" -}}
{{- toYaml .Values.podSecurityContext -}}
{{- end -}}

{{/*
Restricted-compliant container securityContext.
Usage: include "draftforge.containerSecurity" (list <uid> <gid>)
*/}}
{{- define "draftforge.containerSecurity" -}}
runAsNonRoot: true
runAsUser: {{ index . 0 }}
runAsGroup: {{ index . 1 }}
allowPrivilegeEscalation: false
capabilities:
  drop:
    - ALL
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{/*
envFrom list: the draftforge-env ConfigMap, the draftforge-env Secret when the
chart creates it, then each extraEnvSecrets entry. Takes the root context.
*/}}
{{- define "draftforge.envFrom" -}}
- configMapRef:
    name: {{ include "draftforge.fullname" . }}-env
{{- if .Values.secrets.create }}
- secretRef:
    name: {{ include "draftforge.fullname" . }}-env
{{- end }}
{{- range .Values.extraEnvSecrets }}
- secretRef:
    name: {{ . }}
{{- end }}
{{- end -}}

{{/*
Pod spec fields shared by every pod: priority class (when set), no API token,
the chart's ServiceAccount, pull secrets and the pod securityContext.
Takes the root context.
*/}}
{{- define "draftforge.podCommon" -}}
{{- with .Values.priorityClassName -}}
priorityClassName: {{ . }}
{{ end -}}
automountServiceAccountToken: false
serviceAccountName: {{ include "draftforge.fullname" . }}
{{- with .Values.image.pullSecrets }}
imagePullSecrets:
{{- range . }}
  - name: {{ . }}
{{- end }}
{{- end }}
securityContext:
  {{- include "draftforge.podSecurity" . | nindent 2 }}
{{- end -}}

{{/*
Pod template annotations: config/secret checksums, plus
draftforge.kettle.sh/commit when previewCommit is set. Takes the root context.
*/}}
{{- define "draftforge.podAnnotations" -}}
checksum/config: {{ include (print .Template.BasePath "/configmap-env.yaml") . | sha256sum }}
{{- if .Values.secrets.create }}
checksum/secret: {{ include (print .Template.BasePath "/secret.yaml") . | sha256sum }}
{{- end }}
{{- with .Values.previewCommit }}
draftforge.kettle.sh/commit: {{ . | quote }}
{{- end }}
{{- end -}}

{{/*
Fail the render unless a container sets cpu, memory and ephemeral-storage
requests and limits (the preview quota covers those keys, and admission rejects
a pod without them). Emits the resources block.
Usage: include "draftforge.requireResources" (dict "name" "backend" "res" .Values.backend.resources)
*/}}
{{- define "draftforge.requireResources" -}}
{{- $res := .res | default dict -}}
{{- range $key := list "requests.cpu" "requests.memory" "requests.ephemeral-storage" "limits.cpu" "limits.memory" "limits.ephemeral-storage" -}}
{{- $parts := splitList "." $key -}}
{{- if not (dig (index $parts 0) (index $parts 1) "" $res) -}}
{{- fail (printf "draftforge: container %q must set resources.%s" $.name $key) -}}
{{- end -}}
{{- end -}}
{{- toYaml $res -}}
{{- end -}}

{{/*
The env ConfigMap keys the chart manages, as YAML. configmap-env.yaml renders
them, and the guard refuses an env.extra key that names one. Takes the root
context.
*/}}
{{- define "draftforge.envChartData" -}}
{{- $host := .Values.ingress.host | default "" -}}
{{- $siteUrl := .Values.env.siteUrl | default (ternary (printf "https://%s" $host) "" (ne $host "")) -}}
{{- $data := dict
  "NODE_ENV" .Values.env.nodeEnv
  "DEBUG" .Values.env.debug
  "TEST" .Values.env.test
  "RELEASE" .Values.env.release
  "CI" .Values.env.ci
  "SITE_URL" $siteUrl
  "OTEL_ENABLED" .Values.env.otelEnabled
  "LOG_FORMAT" .Values.env.logFormat
  "LOG_LEVEL" .Values.env.logLevel
  "REDIS_HOST" "redis"
  "CELERY_BROKER_URL" "redis://redis:6379/3"
  "CELERY_RESULT_BACKEND" "redis://redis:6379/3"
  "INTERNAL_API_URL" "http://backend:8000/api/internal"
  "API_BASE_URL" "http://backend:8000/api"
  "SQLITE_PATH" "/data/db.sqlite3"
  "EXTRA_ALLOWED_HOSTS" $host
  "EXTRA_CSRF_TRUSTED_ORIGINS" (ternary (printf "https://%s" $host) "" (ne $host ""))
  "TRUST_X_FORWARDED_PROTO" "true"
  "DEPLOY_VERSION" (include "draftforge.imageTag" .)
-}}
{{- toYaml $data -}}
{{- end -}}
