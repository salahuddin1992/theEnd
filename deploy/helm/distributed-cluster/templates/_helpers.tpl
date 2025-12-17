{{/*
Expand the name of the chart.
*/}}
{{- define "distributed-cluster.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "distributed-cluster.fullname" -}}
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
{{- define "distributed-cluster.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "distributed-cluster.labels" -}}
helm.sh/chart: {{ include "distributed-cluster.chart" . }}
{{ include "distributed-cluster.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "distributed-cluster.selectorLabels" -}}
app.kubernetes.io/name: {{ include "distributed-cluster.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Master labels
*/}}
{{- define "distributed-cluster.master.labels" -}}
{{ include "distributed-cluster.labels" . }}
app.kubernetes.io/component: master
{{- end }}

{{/*
Master selector labels
*/}}
{{- define "distributed-cluster.master.selectorLabels" -}}
{{ include "distributed-cluster.selectorLabels" . }}
app.kubernetes.io/component: master
{{- end }}

{{/*
Worker labels
*/}}
{{- define "distributed-cluster.worker.labels" -}}
{{ include "distributed-cluster.labels" . }}
app.kubernetes.io/component: worker
{{- end }}

{{/*
Worker selector labels
*/}}
{{- define "distributed-cluster.worker.selectorLabels" -}}
{{ include "distributed-cluster.selectorLabels" . }}
app.kubernetes.io/component: worker
{{- end }}

{{/*
GPU Worker labels
*/}}
{{- define "distributed-cluster.gpuWorker.labels" -}}
{{ include "distributed-cluster.labels" . }}
app.kubernetes.io/component: worker-gpu
{{- end }}

{{/*
GPU Worker selector labels
*/}}
{{- define "distributed-cluster.gpuWorker.selectorLabels" -}}
{{ include "distributed-cluster.selectorLabels" . }}
app.kubernetes.io/component: worker-gpu
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "distributed-cluster.serviceAccountName" -}}
{{- if .Values.security.serviceAccount.create }}
{{- default (include "distributed-cluster.fullname" .) .Values.security.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.security.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Master service URL
*/}}
{{- define "distributed-cluster.masterUrl" -}}
http://{{ include "distributed-cluster.fullname" . }}-master:{{ .Values.master.service.port }}
{{- end }}
