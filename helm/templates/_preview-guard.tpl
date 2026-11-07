{{/*
Preview-mode guard rails. When preview.enabled is true, fail the render unless
every security-relevant value the home ApplicationSet must set is present. It
protects against a misconfigured ApplicationSet, not against the chart itself.
Included first in every template, so no template renders without it.
Emits nothing. Takes the root context.
*/}}
{{- define "draftforge.previewGuard" -}}
{{- if .Values.preview.enabled -}}
{{- $v := .Values -}}
{{- $ns := .Release.Namespace -}}
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
{{- if $v.persistence.enabled -}}
{{- fail "draftforge preview guard: persistence.enabled must be false" -}}
{{- end -}}
{{- if not $v.priorityClassName -}}
{{- fail "draftforge preview guard: priorityClassName must be set" -}}
{{- end -}}
{{- if not $v.preview.networkPolicy.ingressNamespace -}}
{{- fail "draftforge preview guard: preview.networkPolicy.ingressNamespace must be set" -}}
{{- end -}}
{{- range $key := list "pods" "requestsCpu" "requestsMemory" "limitsMemory" -}}
{{- if not (index $v.preview.quota $key) -}}
{{- fail (printf "draftforge preview guard: preview.quota.%s must be set" $key) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
