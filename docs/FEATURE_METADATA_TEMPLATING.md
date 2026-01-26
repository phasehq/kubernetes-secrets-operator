# Metadata Templating for Managed Secrets

## Overview

The Phase Kubernetes Secrets Operator now supports adding custom labels and annotations to managed Kubernetes Secrets through the `template.metadata` field in `PhaseSecret` custom resources.

This feature enables seamless integration with tools like ArgoCD, Cert-Manager, and Prometheus that require specific labels or annotations on Secret resources.

## Features

✅ **User-Defined Labels**: Add custom labels to managed secrets  
✅ **User-Defined Annotations**: Add operational metadata via annotations  
✅ **Operator-Managed Labels**: KEP-1623 recommended labels automatically applied  
✅ **Reserved Namespace Protection**: `secrets.phase.dev/*` labels are protected  
✅ **Metadata-Only Updates**: Updates trigger reconciliation without data changes  
✅ **Backward Compatible**: Existing PhaseSecrets without template continue to work  
✅ **Per-Secret Configuration**: Different metadata for each managed secret  

## API Specification

### Schema

```yaml
apiVersion: secrets.phase.dev/v1alpha1
kind: PhaseSecret
spec:
  managedSecretReferences:
    - secretName: my-secret
      secretNamespace: default
      secretType: Opaque
      
      # New: template field
      template:
        metadata:
          labels:
            # Custom labels (string key-value pairs)
            key: value
          annotations:
            # Custom annotations (string key-value pairs)
            key: value
```

### Operator-Managed Labels (Always Present)

Following [KEP-1623](https://github.com/kubernetes/enhancements/tree/master/keps/sig-apps/1623-standardize-labels) recommended labels:

| Label | Value | Description |
|-------|-------|-------------|
| `app.kubernetes.io/name` | `phase-secret` | Component name |
| `app.kubernetes.io/instance` | `<secret-name>` | Unique instance identifier |
| `app.kubernetes.io/managed-by` | `phase-secrets-operator` | Managing tool |
| `app.kubernetes.io/component` | `secret` | Component type |
| `secrets.phase.dev/phasesecret` | `<cr-name>` | Owning PhaseSecret CR |
| `secrets.phase.dev/managed` | `true` | Managed by operator flag |

### Operator-Managed Annotations (Always Present)

| Annotation | Value | Description |
|------------|-------|-------------|
| `secrets.phase.dev/last-sync` | ISO 8601 timestamp | Last successful sync time |

## Use Cases

### 1. ArgoCD Cluster Secrets

ArgoCD requires the label `argocd.argoproj.io/secret-type: cluster` on cluster credential secrets.

```yaml
apiVersion: secrets.phase.dev/v1alpha1
kind: PhaseSecret
metadata:
  name: argocd-production-cluster
  namespace: argocd
spec:
  phaseApp: "infrastructure"
  phaseAppEnv: "production"
  phaseHost: "https://console.phase.dev"
  
  authentication:
    serviceToken:
      serviceTokenSecretReference:
        secretName: phase-service-token
        secretNamespace: default
  
  managedSecretReferences:
    - secretName: prod-eks-cluster
      secretNamespace: argocd
      secretType: Opaque
      template:
        metadata:
          labels:
            argocd.argoproj.io/secret-type: cluster
            environment: production
          annotations:
            description: "Production EKS cluster credentials"
```

**Verification:**
```bash
# Check ArgoCD recognizes the cluster
argocd cluster list

# Verify labels
kubectl get secret prod-eks-cluster -n argocd -o jsonpath='{.metadata.labels}'
```

### 2. Cert-Manager Integration

Cert-Manager uses labels to associate secrets with certificates.

```yaml
apiVersion: secrets.phase.dev/v1alpha1
kind: PhaseSecret
metadata:
  name: tls-certificate
  namespace: cert-manager
spec:
  phaseApp: "tls-certificates"
  phaseAppEnv: "production"
  phaseHost: "https://console.phase.dev"
  
  authentication:
    serviceToken:
      serviceTokenSecretReference:
        secretName: phase-service-token
        secretNamespace: default
  
  managedSecretReferences:
    - secretName: example-com-tls
      secretNamespace: default
      secretType: kubernetes.io/tls
      template:
        metadata:
          labels:
            cert-manager.io/certificate-name: example-com
            cert-manager.io/common-name: "example.com"
          annotations:
            cert-manager.io/alt-names: "*.example.com,example.com"
```

### 3. Prometheus ServiceMonitor Discovery

Enable Prometheus to discover and scrape secrets metadata.

```yaml
template:
  metadata:
    labels:
      prometheus.io/scrape: "true"
      prometheus.io/path: "/metrics"
    annotations:
      prometheus.io/port: "8080"
```

### 4. Organizational Tagging

Add team, cost-center, and environment labels for resource management.

```yaml
template:
  metadata:
    labels:
      team: platform-engineering
      cost-center: infrastructure
      environment: production
      region: us-east-1
    annotations:
      contact: "platform-team@example.com"
      oncall: "https://oncall.example.com/platform"
      runbook: "https://wiki.example.com/runbooks/secret-rotation"
```

## Validation Rules

### Label Restrictions

1. **Reserved Namespace**: Labels starting with `secrets.phase.dev/` cannot be set by users
   - Attempting to set reserved labels will log a warning and skip them
   - Example: `secrets.phase.dev/custom: value` ❌

2. **Protected Labels**: Operator-managed labels cannot be overridden
   - `app.kubernetes.io/managed-by` ❌
   - `app.kubernetes.io/name` ❌

3. **Label Key Format**: Must follow [DNS subdomain format](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/#syntax-and-character-set) (RFC 1123)
   - Valid: `example.com/my-label` ✅
   - Invalid: `example.com/my_label` ❌

4. **Label Value Length**: Maximum 63 characters

### Annotation Restrictions

- **No restrictions** on annotation keys
- Maximum total size: **256KB** per secret
- Can contain structured data (JSON, YAML)

## Migration Guide

### From Secrets Without Metadata

**Before:**
```yaml
apiVersion: secrets.phase.dev/v1alpha1
kind: PhaseSecret
metadata:
  name: my-app-secrets
spec:
  phaseApp: "my-app"
  managedSecretReferences:
    - secretName: app-credentials
      secretNamespace: default
      secretType: Opaque
```

**After:**
```yaml
apiVersion: secrets.phase.dev/v1alpha1
kind: PhaseSecret
metadata:
  name: my-app-secrets
spec:
  phaseApp: "my-app"
  managedSecretReferences:
    - secretName: app-credentials
      secretNamespace: default
      secretType: Opaque
      template:  # Added
        metadata:
          labels:
            environment: production
          annotations:
            contact: team@example.com
```

### From External Secrets Operator

The API is compatible with External Secrets Operator's `spec.target.template.metadata` pattern.

**External Secrets:**
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
spec:
  target:
    template:
      metadata:
        labels:
          key: value
```

**Phase Secrets:**
```yaml
apiVersion: secrets.phase.dev/v1alpha1
kind: PhaseSecret
spec:
  managedSecretReferences:
    - template:
        metadata:
          labels:
            key: value
```

## Reconciliation Behavior

### When Does Reconciliation Trigger?

1. **Data Changes**: Secret data in Phase environment is updated
2. **Metadata Changes**: Labels or annotations in CR template are modified
3. **Polling Interval**: Every 60 seconds (default) or custom `pollingInterval`

### Update Strategy

- **Atomic Updates**: Uses `replace_namespaced_secret()` for consistency
- **No Downtime**: Secrets are updated in-place
- **Metadata-Only Updates**: Changing only labels/annotations doesn't trigger data re-fetch

## Security Considerations

### Reserved Namespace Protection

The `secrets.phase.dev/*` namespace is reserved to prevent:
- **Label Spoofing**: Cannot fake ownership by setting `secrets.phase.dev/phasesecret`
- **Metadata Tampering**: Operator-managed labels maintain integrity

### RBAC Requirements

The operator ServiceAccount requires these permissions:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: phase-secrets-operator
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["secrets.phase.dev"]
    resources: ["phasesecrets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["secrets.phase.dev"]
    resources: ["phasesecrets/status"]
    verbs: ["update", "patch"]
```

### Audit Trail

Every managed secret includes:
- `secrets.phase.dev/last-sync`: Timestamp of last modification
- `app.kubernetes.io/managed-by`: Operator identifier
- `secrets.phase.dev/phasesecret`: Link to owning CR

## Troubleshooting

### Labels Not Applied

**Symptom**: User-defined labels don't appear on secret

**Possible Causes**:
1. Label uses reserved namespace `secrets.phase.dev/*`
2. Label key format is invalid (RFC 1123)
3. Label value exceeds 63 characters

**Solution**:
```bash
# Check operator logs for warnings
kubectl logs -n phase-operator deployment/phase-secrets-operator

# Look for:
# "Skipping user-defined label 'secrets.phase.dev/custom': reserved namespace"
# "Skipping user-defined label 'app.kubernetes.io/managed-by': managed by operator"
```

### Metadata Changes Not Reflected

**Symptom**: Updated labels in CR don't sync to secret

**Solution**:
```bash
# Check reconciliation interval
kubectl get phasesecret <name> -o jsonpath='{.spec.pollingInterval}'

# Force immediate sync by updating a label on the CR
kubectl label phasesecret <name> sync-trigger="$(date +%s)"

# Check operator logs
kubectl logs -n phase-operator deployment/phase-secrets-operator | grep "metadata"
```

### ArgoCD Not Recognizing Secret

**Symptom**: ArgoCD cluster list doesn't show the secret

**Required Label**: `argocd.argoproj.io/secret-type: cluster`

**Verification**:
```bash
# Check label is present
kubectl get secret <name> -n argocd -o jsonpath='{.metadata.labels.argocd\.argoproj\.io/secret-type}'
# Expected: cluster

# If missing, verify PhaseSecret CR template:
kubectl get phasesecret <name> -o yaml | grep -A 5 "template:"
```

## Performance Considerations

- **Metadata-Only Updates**: Fast, no Phase API call required
- **Label Merging**: O(n) where n = number of user labels (typically < 10)
- **Memory Overhead**: ~100 bytes per label, ~500 bytes per annotation

## CNCF Best Practices

This feature implements:

✅ **KEP-1623**: Standard label names and values  
✅ **Declarative Configuration**: Full state in CR  
✅ **Idempotency**: Reconciliation is repeatable  
✅ **Least Privilege**: Namespace-scoped by default  
✅ **Observability**: Audit trail via annotations  
✅ **API Conventions**: Follows Kubernetes object metadata patterns  

## References

- [Kubernetes Labels and Selectors](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/)
- [Kubernetes Annotations](https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/)
- [KEP-1623: Standardize Labels](https://github.com/kubernetes/enhancements/tree/master/keps/sig-apps/1623-standardize-labels)
- [External Secrets Operator Template](https://external-secrets.io/latest/api/externalsecret/#template)
- [ArgoCD Cluster Secrets](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/#clusters)
- [Issue #39](https://github.com/phasehq/kubernetes-secrets-operator/issues/39)