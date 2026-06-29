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
- Added `spec.onSecretReferenceError` (`Fail` default, `Warn`) to control whether an unresolved `${...}` reference aborts the sync or is synced as-is; both modes record a Warning event on the `PhaseSecret`.
- Reconcile each managed secret reference independently so one failing reference no longer blocks the others in the same `PhaseSecret`.

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

## Upgrading from v1

The v1 (Kopf) operator added a `kopf.zalando.org/KopfFinalizerMarker` finalizer to every `PhaseSecret`. The Go operator does not use it, so after upgrading you must remove it once from existing resources — otherwise deleting a `PhaseSecret` later will hang in `Terminating`. See the [Kubernetes integration upgrade guide](https://docs.phase.dev/integrations/platforms/kubernetes) for the full step-by-step procedure (apply the CRD, `helm upgrade`, remove the finalizer).

## Reference Resolution

By default the operator fails a sync when a `${...}` reference cannot be resolved, so a broken value is never written to a workload; it records a Warning event naming the affected secret. Set `onSecretReferenceError: Warn` on a `PhaseSecret` to instead sync with unresolved references left as their literal `${...}` text. This is a behavior change from v1, which always synced unresolved references as-is.

## Service Account Token Secrets

Kubernetes `kubernetes.io/service-account-token` Secrets require an annotation naming the service account:

```yaml
template:
  metadata:
    annotations:
      kubernetes.io/service-account.name: my-service-account
```

Without this annotation, Kubernetes rejects or cannot populate the special service-account-token Secret. This was also a limitation of the legacy operator.
