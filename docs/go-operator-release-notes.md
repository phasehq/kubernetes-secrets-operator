# Go Operator Release Notes

This release rewrites the Phase Kubernetes Secrets Operator from Python/Kopf to Go/controller-runtime while keeping the `secrets.phase.dev/v1alpha1` `PhaseSecret` API compatible with existing resources.

## What Changed

- Replaced the Kopf daemon loop with a controller-runtime reconciler.
- Preserved the local sync checkpoint behavior so full secret reads are skipped when the Phase environment metadata and CR spec are unchanged.
- Updated managed Kubernetes Secrets atomically instead of delete/recreate by default.
- Added exact app targeting with `spec.phaseAppId`.
- Added per-managed-secret metadata passthrough with `managedSecretReferences[].template.metadata.labels` and `.annotations`.
- Added `spec.redeployLabelSelector` to narrow auto-redeploy Deployment scans.
- Added Helm knobs for retries, backoff, and reconcile concurrency.

## Compatibility

Existing `PhaseSecret` resources continue to work. The legacy fields remain supported:

- `phaseApp`
- `phaseAppEnv`
- `phaseAppEnvPath`
- `phaseAppEnvTag`
- `phaseHost`
- `pollingInterval`
- `authentication.serviceToken.serviceTokenSecretReference`
- `managedSecretReferences`
- processors and name transformers

The Go operator still supports legacy auto-redeploy behavior:

- Deployment metadata annotation `secrets.phase.dev/redeploy`
- Matching `containers[].envFrom[].secretRef.name`
- Patching pod template annotation `phase.autoredeploy.timestamp`

## CRD Upgrade Note

Helm does not upgrade CRDs in `crds/` automatically. Apply the updated CRD before using new fields:

```sh
kubectl apply -f crd-template.yaml
```

## Service Account Token Secrets

Kubernetes `kubernetes.io/service-account-token` Secrets require an annotation naming the service account:

```yaml
template:
  metadata:
    annotations:
      kubernetes.io/service-account.name: my-service-account
```

Without this annotation, Kubernetes rejects or cannot populate the special service-account-token Secret. This was also a limitation of the legacy operator.
