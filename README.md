# Phase Kubernetes Operator

### Securely sync secrets and environment variables with Phase in your Kubernetes cluster.

```
           /$$
          | $$
  /$$$$$$ | $$$$$$$   /$$$$$$   /$$$$$$$  /$$$$$$
 /$$__  $$| $$__  $$ |____  $$ /$$_____/ /$$__  $$
| $$  \ $$| $$  \ $$  /$$$$$$$|  $$$$$$ | $$$$$$$$
| $$  | $$| $$  | $$ /$$__  $$ \____  $$| $$_____/
| $$$$$$$/| $$  | $$|  $$$$$$$ /$$$$$$$/|  $$$$$$$
| $$____/ |__/  |__/ \_______/|_______/  \_______/
| $$
|__/
```

## Features

- Automatically sync secrets to your Kubernetes cluster
- End-to-End encryption
- Automatically redeploy deployments when a secret is updated
- Sync secrets based on environment (dev, staging, prod), folders and tags
- Transform secrets via secret processors
- Target Phase apps by exact app ID with `phaseAppId`
- Add labels and annotations to managed Kubernetes Secrets
- Update managed Secrets atomically without a delete/recreate gap

```yaml
metadata:
  annotations:
    secrets.phase.dev/redeploy: "true"
```

## Installation:

### 1. Install the Operator via Helm

Add the Phase Helm repository and update it:

```fish
helm repo add phase https://helm.phase.dev && helm repo update
```

Install the Phase Secrets Operator:

```fish
helm install phase-secrets-operator phase/phase-kubernetes-operator --set image.tag=v2.0.0
```

    It's best practice to specify the version in production environments to avoid
    unintended upgrades. Find available versions on our [GitHub
    releases](https://github.com/phasehq/kubernetes-secrets-operator/releases).

### 2. Create a Service Token Secret in Kubernetes

Securely create a Service Token Secret using `read` (recommended for more security as it avoids writing the token to disk or shell history)

Run this command, paste the Phase Service Token and hit enter:

```fish
read -s TOKEN
kubectl create secret generic phase-service-token \
  --from-literal=token=$TOKEN \
  --type=Opaque \
  --namespace=default
unset TOKEN
```

Alternatively, create it directly using `kubectl`:

```fish
kubectl create secret generic phase-service-token \
  --from-literal=token=<TOKEN> \
  --type=Opaque \
  --namespace=default
```

### 3. Deploy the Phase Secrets Operator CR (Custom Resource)

Create a custom resource file: `phase-secrets-operator-cr.yaml`

```yaml
apiVersion: secrets.phase.dev/v1alpha1
kind: PhaseSecret
metadata:
  name: example-phase-secret
  namespace: default
spec:
  phaseApp: "the-name-of-your-phase-app" # The name of your Phase application
  # phaseAppId: "your-phase-app-id" # OPTIONAL - use an exact app ID instead of name matching
  phaseAppEnv: "prod" # OPTIONAL - The Phase application environment to fetch secrets from
  phaseAppEnvPath: "/" # OPTIONAL - Folder path to fetch from
  phaseAppEnvTag: "backend" # OPTIONAL - Tag filter
  phaseHost: "https://console.phase.dev" # OPTIONAL - URL of the Phase Console instance
  pollingInterval: 60 # OPTIONAL - Minimum 5 seconds
  redeployLabelSelector: "app=my-application" # OPTIONAL - narrow Deployment scans for auto-redeploy
  authentication:
    serviceToken:
      serviceTokenSecretReference:
        secretName: "phase-service-token" # Name of the service token with access to your Phase application
        secretNamespace: "default"
  managedSecretReferences:
    - secretName: "my-application-secret" # Name of the Kubernetes managed secret that Phase will sync
      secretNamespace: "default"
      secretType: Opaque
      # nameTransformer: lower-snake
      # template:
      #   metadata:
      #     labels:
      #       argocd.argoproj.io/secret-type: cluster
      #     annotations:
      #       example.com/owner: platform
```

Deploy the custom resource:

```fish
kubectl apply -f phase-secrets-operator-cr.yaml
```

Watch for `my-application-secret` managed secret being created:

```fish
watch kubectl get secrets
```

View the secrets:

```fish
kubectl get secret my-application-secret -o yaml
```

    The operator automatically synchronizes secrets every 60 seconds.

[Phase Kubernetes Operator - Docs](https://docs.phase.dev/integrations/platforms/kubernetes)


## Configuration Notes

### Exact App Selection

Use `phaseAppId` when you want to avoid partial-name matching:

```yaml
spec:
  phaseAppId: "b6ad8824-7133-4839-8013-f87c2182fc61"
```

If both `phaseApp` and `phaseAppId` are set, `phaseAppId` takes precedence.

### Managed Secret Metadata

You can pass labels and annotations through to each managed Kubernetes Secret:

```yaml
spec:
  managedSecretReferences:
    - secretName: "argocd-cluster"
      secretNamespace: "argocd"
      secretType: Opaque
      template:
        metadata:
          labels:
            argocd.argoproj.io/secret-type: cluster
          annotations:
            example.com/owner: platform
```

For `kubernetes.io/service-account-token` Secrets, Kubernetes requires the service account annotation:

```yaml
spec:
  managedSecretReferences:
    - secretName: "phase-managed-sa-token"
      secretNamespace: "default"
      secretType: kubernetes.io/service-account-token
      template:
        metadata:
          annotations:
            kubernetes.io/service-account.name: "my-service-account"
```

### Auto-Redeploy

Deployments opt in by setting the annotation below on the Deployment metadata:

```yaml
metadata:
  annotations:
    secrets.phase.dev/redeploy: "true"
```

When a managed Secret changes, the operator patches matching Deployments with
`phase.autoredeploy.timestamp` on the pod template. Matching is based on
`containers[].envFrom[].secretRef.name`, preserving the legacy behavior.

Use `spec.redeployLabelSelector` to reduce Deployment list work in namespaces with many Deployments.

### Helm Values

The chart exposes operator runtime knobs through `operator.env`:

```yaml
operator:
  env:
    PHASE_VERIFY_SSL: "True"
    PHASE_DEBUG: "False"
    PHASE_OPERATOR_HTTP_RETRIES: "5"
    PHASE_OPERATOR_HTTP_BACKOFF: "1"
    PHASE_OPERATOR_MAX_CONCURRENT_RECONCILES: "4"
```

### Upgrading from v1 to v2

Helm does not upgrade CRDs automatically. Apply the v2 CRD from the chart `crds/` directory before upgrading:

```fish
kubectl apply -f https://raw.githubusercontent.com/phasehq/kubernetes-secrets-operator/v2.0.0/phase-kubernetes-operator/crds/crd-template.yaml
```

Upgrade the release:

```fish
helm repo update phase
helm upgrade phase-secrets-operator phase/phase-kubernetes-operator --set image.tag=v2.0.0
```

Existing managed Secrets are preserved and the Go operator performs one full resync on startup. Existing v1 `PhaseSecret` resources may still have the legacy Kopf finalizer; remove it once after upgrading so future deletes do not hang:

```fish
kubectl get phasesecrets.secrets.phase.dev -A \
  -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name --no-headers |
while read ns name; do
  kubectl patch phasesecret "$name" -n "$ns" --type=json \
    -p '[{"op":"remove","path":"/metadata/finalizers"}]'
done
```

### Design decisions

- Managed Secrets are updated in place. If Kubernetes rejects an update, the existing Secret is left untouched and the operator retries later; Secret availability is preferred over forced delete/recreate.
- Changing immutable Secret fields such as `type` may require manually deleting and recreating the Secret.
- `template.metadata` labels/annotations are merged into existing Secret metadata. Removing a key from the CR does not remove it from an existing Secret.
- `type: base64` expects a base64 value in Phase and preserves the workload-facing Kubernetes Secret payload.
- Unresolved `${...}` references are synced as-is by design.
- Auto-redeploy requires `secrets.phase.dev/redeploy`, an `envFrom.secretRef` match, and a changed managed Secret.
- Service token and managed Secret namespaces are explicit; auto-redeploy scans Deployments in the `PhaseSecret` namespace.

## Development:

1. Run the Go test suite

```
go test ./...
```

2. Create a local kind cluster (skip if you have one already setup)

```fish
kind create cluster
```

3. Export kindconfig

```
kind get kubeconfig --name "kind" > ~/.kube/config
```

Verify that the cluster is up:

```
kubectl get nodes
```

4. Create a copy of the CR (Custom Resource) and CRD (Custom Resource Definition):

```
cp cr-template.yaml dev-cr.yaml
```

```
cp crd-template.yaml dev-crd.yaml
```

Feel free to make changes

5. Create a secret in kubernetes containing the Phase Service Token

```fish
kubectl create secret generic phase-service-token \
 --from-literal=token=<YOUR_PHASE_SERVICE_TOKEN> \
 --type=Opaque \
 --namespace=default
```

6. Apply the CRD and CR respectively

```fish
kubectl apply -f dev-crd.yaml
```

```fish
kubectl apply -f dev-cr.yaml
```

7. Start the operator locally

```fish
go run ./cmd/manager
```

8. Build the operator container

```fish
docker build -t phase-kubernetes-operator-go:test .
```

9. Install the local chart into minikube

```fish
minikube image load phase-kubernetes-operator-go:test
helm upgrade --install phase-secrets-operator ./phase-kubernetes-operator \
  --namespace phase-operator \
  --create-namespace \
  --set image.repository=phase-kubernetes-operator-go \
  --set image.tag=test \
  --set image.pullPolicy=Never
```
