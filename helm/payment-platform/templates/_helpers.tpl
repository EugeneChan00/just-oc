{{/*
Expand the name of the chart.
*/}}
{{- define "payment-platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "payment-platform.fullname" -}}
{{- $name := include "payment-platform.name" . }}
{{- .Release.Namespace | printf "%s-%s" $name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "payment-platform.labels" -}}
app.kubernetes.io/name: {{ include "payment-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/part-of: payment-platform
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "payment-platform.selectorLabels" -}}
app.kubernetes.io/name: {{ include "payment-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name
*/}}
{{- define "payment-platform.serviceAccountName" -}}
{{- .Values.serviceAccount.name | default "payment-platform" }}
{{- end }}
