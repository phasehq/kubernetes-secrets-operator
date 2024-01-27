# Phase Kubernetes Operator

### Securely sync secrets and environment variables with Phase in your Kubernetes cluster.

```
⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⠔⠋⣳⣖⠚⣲⢖⠙⠳⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⡴⠉⢀⡼⠃⢘⣞⠁⠙⡆⠀⠘⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⢀⡜⠁⢠⠞⠀⢠⠞⠸⡆⠀⠹⡄⠀⠹⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⢀⠞⠀⢠⠏⠀⣠⠏⠀⠀⢳⠀⠀⢳⠀⠀⢧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⢠⠎⠀⣠⠏⠀⣰⠃⠀⠀⠀⠈⣇⠀⠘⡇⠀⠘⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⢠⠏⠀⣰⠇⠀⣰⠃⠀⠀⠀⠀⠀⢺⡀⠀⢹⠀⠀⢽⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⢠⠏⠀⣰⠃⠀⣰⠃⠀⠀⠀⠀⠀⠀⠀⣇⠀⠈⣇⠀⠘⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⢠⠏⠀⢰⠃⠀⣰⠃⠀⠀⠀⠀⠀⠀⠀⠀⢸⡀⠀⢹⡀⠀⢹⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⢠⠏⠀⢰⠃⠀⣰⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣇⠀⠈⣇⠀⠈⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠛⠒⠚⠛⠒⠓⠚⠒⠒⠓⠒⠓⠚⠒⠓⠚⠒⠓⢻⡒⠒⢻⡒⠒⢻⡒⠒⠒⠒⠒⠒⠒⠒⠒⠒⣲⠒⠒⣲⠒⠒⡲⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢧⠀⠀⢧⠀⠈⣇⠀⠀⠀⠀⠀⠀⠀⠀⢠⠇⠀⣰⠃⠀⣰⠃⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⡆⠀⠘⡆⠀⠸⡄⠀⠀⠀⠀⠀⠀⣠⠇⠀⣰⠃⠀⣴⠃⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠹⡄⠀⠹⡄⠀⠹⡄⠀⠀⠀⠀⡴⠃⢀⡼⠁⢀⡼⠁⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⣆⠀⠙⣆⠀⠹⣄⠀⣠⠎⠁⣠⠞⠀⡤⠏⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠳⢤⣈⣳⣤⣼⣹⢥⣰⣋⡥⡴⠊⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀

```

## Features

- Automatically sync secrets to your Kubernetes cluster
- End-to-End encryption
- Automatically redeploy deployments when a secret is updated
- Sync secrets based on environment (dev, staging, prod) and tags
- Transform secrets via secret processors

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
helm install phase-secrets-operator phase/phase-kubernetes-operator --set image.tag=v1.0.1
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
  phaseAppEnv: "prod" # OPTIONAL - The Phase application environment to fetch secrets from
  phaseHost: "https://console.phase.dev" # OPTIONAL - URL of the Phase Console instance
  authentication:
    serviceToken:
      serviceTokenSecretReference:
        secretName: "phase-service-token" # Name of the service token with access to your Phase application
        secretNamespace: "default"
  managedSecretReferences:
    - secretName: "my-application-secret" # Name of the Kubernetes managed secret that Phase will sync
      secretNamespace: "default"
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

## Development:

1. Install python dependencies

```
pip3 install -r requirements.txt
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

7. Start the operator via Kopf

```fish
kopf run src/main.py
```
