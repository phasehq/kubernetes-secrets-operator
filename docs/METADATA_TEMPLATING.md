# Managed Secret Metadata Templating

## Overview

The Phase Kubernetes Secrets Operator supports metadata templating for managed Kubernetes Secrets, allowing you to attach custom labels and annotations to secrets created from Phase. This feature is essential for integrating with tools like ArgoCD, Cert-Manager, and other Kubernetes-native applications that rely on specific metadata.

## Motivation

Many Kubernetes applications require specific labels or annotations on Secret resources:

- **ArgoCD**: Requires `argocd.argoproj.io/secret-type: cluster` label for cluster secrets
- **Cert-Manager**: Uses `cert-manager.io/*` labels and annotations for certificate management
- **Prometheus**: Uses `prometheus.io/scrape` labels for service discovery
- **Custom Operators**: May require specific metadata for their operation

Without this feature, secrets created by Phase would not have the necessary metadata, causing integration failures.

## Design Principles

This feature follows CNCF and Kubernetes best practices:

1. **API Compatibility**: Mirrors [External Secrets Operator](https://external-secrets.io/latest/api/externalsecret/#template) pattern for familiarity
2. **Declarative Configuration**: All metadata is defined in the PhaseSecret CR spec
3. **Operator-Managed Labels**: Reserved labels are always set and cannot be overridden
4. **Namespace Isolation**: `secrets.phase.dev/*` namespace is reserved for operator use
5. **KEP-1623 Compliance**: Follows [Kubernetes recommended labels](https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/)

## Usage

### Basic Example

```yaml
apiVersion: secrets.phase.dev/v1alpha1
kind: PhaseSecret
metadata:
  name: my-secret
  namespace: default
spec:
  phaseApp: "my-app"
  phaseAppEnv: "production"
  
  managedSecretReferences:
    - secretName: app-credentials
      secretNamespace: default
      secretType: Opaque
      
      # Add metadata template
      template:
        metadata:
          labels:
            environment: production
            team: backend
          annotations:
            description: "Application credentials"
            owner: backend-team@example.com
```

### ArgoCD Integration

```yaml
template:
  metadata:
    labels:
      argocd.argoproj.io/secret-type: cluster
      environment: production
    annotations:
      managed-by: phase-operator
```

### Cert-Manager Integration

```yaml
template:
  metadata:
    labels:
      cert-manager.io/certificate-name: my-cert
    annotations:
      cert-manager.io/common-name: example.com
      cert-manager.io/issuer-name: letsencrypt-prod
```

## Metadata Merging Behavior

### Operator-Managed Labels (Always Present)

These labels are automatically added by the operator and **cannot be overridden**:

| Label | Value | Purpose |
|-------|-------|----------|
| `app.kubernetes.io/name` | `phase-secret` | Identifies the application |
| `app.kubernetes.io/instance` | `<secret-name>` | Unique instance identifier |
| `app.kubernetes.io/managed-by` | `phase-secrets-operator` | Identifies the managing controller |
| `app.kubernetes.io/component` | `secret` | Component type |
| `secrets.phase.dev/phasesecret` | `<cr-name>` | Links to owning PhaseSecret CR |
| `secrets.phase.dev/managed` | `true` | Marks as operator-managed |

### Operator-Managed Annotations

These annotations are automatically added:

| Annotation | Value | Purpose |
|------------|-------|----------|
| `secrets.phase.dev/last-sync` | ISO 8601 timestamp | Last synchronization time |

### User-Defined Metadata

- **Labels**: Merged additively with operator labels. Reserved namespace `secrets.phase.dev/*` is protected.
- **Annotations**: Merged additively with operator annotations. No restrictions on keys.

### Example Merged Metadata

**PhaseSecret CR:**
```yaml
template:
  metadata:
    labels:
      environment: production
      team: platform
    annotations:
      contact: ops@example.com
```

**Resulting Secret:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
  labels:
    # Operator-managed (always present)
    app.kubernetes.io/name: phase-secret
    app.kubernetes.io/instance: my-secret
    app.kubernetes.io/managed-by: phase-secrets-operator
    app.kubernetes.io/component: secret
    secrets.phase.dev/phasesecret: my-phasesecret
    secrets.phase.dev/managed: "true"
    # User-defined (from template)
    environment: production
    team: platform
  annotations:
    # Operator-managed
    secrets.phase.dev/last-sync: "2026-01-27T00:00:00Z"
    # User-defined
    contact: ops@example.com
type: Opaque
data:
  # ... secret data
```

## Validation and Restrictions

### Label Restrictions

1. **Reserved Namespace**: Labels starting with `secrets.phase.dev/` cannot be set by users
2. **Protected Labels**: `app.kubernetes.io/managed-by` and `app.kubernetes.io/name` are protected
3. **Format**: Must follow [Kubernetes label format](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/#syntax-and-character-set)
4. **Length**: Maximum 63 characters for values

### Annotation Restrictions

- No key restrictions (except best practices)
- Maximum total size: 256KB (Kubernetes limit)
- Can contain arbitrary metadata

### CRD Validation

The CRD includes OpenAPI v3 validation:

```yaml
labels:
  type: object
  additionalProperties:
    type: string
    maxLength: 63
    pattern: '^([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9]$'
```

## Reconciliation Behavior

### Metadata-Only Updates

Changing only metadata in the template triggers reconciliation without recreating the secret:

1. Operator detects metadata change in CR
2. Updates Secret using `replace` operation (atomic)
3. Preserves secret data
4. Updates `secrets.phase.dev/last-sync` annotation

### Combined Updates

If both data and metadata change:

1. Both are updated atomically in a single operation
2. Dependent deployments are redeployed (if configured)

## Troubleshooting

### Labels Not Appearing

**Problem**: User-defined labels don't appear on the secret

**Solutions**:
1. Check if label uses reserved namespace: `secrets.phase.dev/*`
2. Check operator logs for warnings: `kubectl logs -n phase-system deployment/phase-operator`
3. Verify label format follows Kubernetes requirements

### ArgoCD Not Recognizing Secret

**Problem**: ArgoCD doesn't list the cluster secret

**Solution**:
```yaml
template:
  metadata:
    labels:
      argocd.argoproj.io/secret-type: cluster  # Required!
```

### Annotations Too Large

**Problem**: Error creating secret with large annotations

**Solution**: Kubernetes limits total annotation size to 256KB. Reduce annotation content.

## Migration from External Secrets Operator

If migrating from External Secrets Operator:

```yaml
# External Secrets Operator
spec:
  target:
    template:
      metadata:
        labels:
          key: value

# Phase Secrets Operator (compatible!)
spec:
  managedSecretReferences:
    - secretName: my-secret
      template:
        metadata:
          labels:
            key: value
```

## API Reference

### PhaseSecret.spec.managedSecretReferences[].template

```yaml
template:
  type: object
  properties:
    metadata:
      type: object
      properties:
        labels:
          type: object
          additionalProperties:
            type: string
        annotations:
          type: object
          additionalProperties:
            type: string
```

## Examples

See the `examples/` directory for complete examples:

- [`argocd-cluster-secret.yaml`](../examples/argocd-cluster-secret.yaml) - ArgoCD cluster integration
- [`cert-manager-tls-secret.yaml`](../examples/cert-manager-tls-secret.yaml) - TLS certificate management
- [`multi-environment.yaml`](../examples/multi-environment.yaml) - Multiple secrets with different metadata

## References

- [Kubernetes Labels and Selectors](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/)
- [Kubernetes Annotations](https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/)
- [KEP-1623: Recommended Labels](https://github.com/kubernetes/enhancements/blob/master/keps/sig-architecture/1623-standardize-labels/README.md)
- [External Secrets Operator Template](https://external-secrets.io/latest/api/externalsecret/#template)
- [ArgoCD Cluster Secrets](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/#clusters)
