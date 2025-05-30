{{/*
Expand the name of the chart.
*/}}
{{- define "phase.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "phase.fullname" -}}
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
{{- define "phase.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "phase.labels" -}}
helm.sh/chart: {{ include "phase.chart" . }}
{{ include "phase.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "phase.selectorLabels" -}}
app.kubernetes.io/name: {{ include "phase.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Return the appropriate apiVersion for deployment.
*/}}
{{- define "phase.deployment.apiVersion" -}}
{{- if semverCompare ">=1.9-0" .Capabilities.KubeVersion.GitVersion -}}
{{- print "apps/v1" -}}
{{- else -}}
{{- print "extensions/v1beta1" -}}
{{- end -}}
{{- end -}}

{{/*
Service Account Name
Determines the name of the service account to be used by deployments.
If serviceAccount.name is set, it uses that value.
Otherwise, if serviceAccount.create is true, it generates a name using the fullname.
If serviceAccount.create is false and serviceAccount.name is not set, it defaults to "default",
which means the pod will use the default service account in the namespace.
However, our deployments will explicitly set serviceAccountName, so if neither
serviceAccount.create nor serviceAccount.name is specified, it will effectively try to use
a service account named "{{ include "phase.fullname" . }}-sa" if create is true, or just "default" if create is false and name is empty.
We want our deployments to *always* specify a serviceAccountName if values.serviceAccount is configured.
*/}}
{{- define "phase.serviceAccountName" -}}
{{- if .Values.serviceAccount.name -}}
{{- .Values.serviceAccount.name | quote -}}
{{- else -}}
{{- if .Values.serviceAccount.create -}}
{{- printf "%s-sa" (include "phase.fullname" .) | quote -}}
{{- else -}}
{{- "" -}}
{{/* This will cause the deployments to omit serviceAccountName if not creating and no name is provided, defaulting to "default" SA in the namespace */}}
{{- end -}}
{{- end -}}
{{- end -}}