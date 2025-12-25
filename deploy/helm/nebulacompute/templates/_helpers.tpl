{{/*
Expand the name of the chart.
*/}}
{{- define "nebulacompute.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "nebulacompute.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "nebulacompute.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "nebulacompute.labels" -}}
helm.sh/chart: {{ include "nebulacompute.chart" . }}
{{ include "nebulacompute.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "nebulacompute.selectorLabels" -}}
app.kubernetes.io/name: {{ include "nebulacompute.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Master labels
*/}}
{{- define "nebulacompute.master.labels" -}}
{{ include "nebulacompute.labels" . }}
app.kubernetes.io/component: master
{{- end }}

{{- define "nebulacompute.master.selectorLabels" -}}
{{ include "nebulacompute.selectorLabels" . }}
app.kubernetes.io/component: master
{{- end }}

{{/*
Worker labels
*/}}
{{- define "nebulacompute.worker.labels" -}}
{{ include "nebulacompute.labels" . }}
app.kubernetes.io/component: worker
{{- end }}

{{- define "nebulacompute.worker.selectorLabels" -}}
{{ include "nebulacompute.selectorLabels" . }}
app.kubernetes.io/component: worker
{{- end }}

{{/*
Web labels
*/}}
{{- define "nebulacompute.web.labels" -}}
{{ include "nebulacompute.labels" . }}
app.kubernetes.io/component: web
{{- end }}

{{- define "nebulacompute.web.selectorLabels" -}}
{{ include "nebulacompute.selectorLabels" . }}
app.kubernetes.io/component: web
{{- end }}

{{/*
Operator labels
*/}}
{{- define "nebulacompute.operator.labels" -}}
{{ include "nebulacompute.labels" . }}
app.kubernetes.io/component: operator
{{- end }}

{{- define "nebulacompute.operator.selectorLabels" -}}
{{ include "nebulacompute.selectorLabels" . }}
app.kubernetes.io/component: operator
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "nebulacompute.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "nebulacompute.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Get the image name
*/}}
{{- define "nebulacompute.image" -}}
{{- $registry := .Values.global.imageRegistry | default "" -}}
{{- $repository := .Values.image.repository -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion -}}
{{- if $registry }}
{{- printf "%s/%s:%s" $registry $repository $tag }}
{{- else }}
{{- printf "%s:%s" $repository $tag }}
{{- end }}
{{- end }}

{{/*
Master image
*/}}
{{- define "nebulacompute.master.image" -}}
{{- if .Values.master.image.repository }}
{{- $tag := .Values.master.image.tag | default .Values.image.tag | default .Chart.AppVersion -}}
{{- printf "%s:%s" .Values.master.image.repository $tag }}
{{- else }}
{{- include "nebulacompute.image" . }}
{{- end }}
{{- end }}

{{/*
Worker image
*/}}
{{- define "nebulacompute.worker.image" -}}
{{- if .Values.worker.image.repository }}
{{- $tag := .Values.worker.image.tag | default .Values.image.tag | default .Chart.AppVersion -}}
{{- printf "%s:%s" .Values.worker.image.repository $tag }}
{{- else }}
{{- include "nebulacompute.image" . }}
{{- end }}
{{- end }}

{{/*
Generate JWT secret
*/}}
{{- define "nebulacompute.jwtSecret" -}}
{{- if .Values.security.auth.jwtSecret }}
{{- .Values.security.auth.jwtSecret }}
{{- else }}
{{- randAlphaNum 64 }}
{{- end }}
{{- end }}

{{/*
Master service URL
*/}}
{{- define "nebulacompute.master.url" -}}
{{- $name := include "nebulacompute.fullname" . -}}
{{- $port := .Values.master.service.port | default 8765 -}}
{{- printf "http://%s-master:%d" $name (int $port) }}
{{- end }}

{{/*
Storage configuration
*/}}
{{- define "nebulacompute.storage.config" -}}
{{- if eq .Values.storage.backend "postgresql" }}
DATABASE_URL: "postgresql://{{ .Values.storage.postgresql.username }}:{{ .Values.storage.postgresql.password }}@{{ .Values.storage.postgresql.host }}:{{ .Values.storage.postgresql.port }}/{{ .Values.storage.postgresql.database }}"
{{- else if eq .Values.storage.backend "redis" }}
REDIS_URL: "redis://:{{ .Values.storage.redis.password }}@{{ .Values.storage.redis.host }}:{{ .Values.storage.redis.port }}/{{ .Values.storage.redis.db }}"
{{- else }}
SQLITE_PATH: "{{ .Values.storage.sqlite.path }}"
{{- end }}
{{- end }}
