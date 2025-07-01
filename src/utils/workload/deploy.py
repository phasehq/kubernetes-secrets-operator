from kubernetes.client.rest import ApiException
from kubernetes.client import AppsV1Api
from utils.const import REDEPLOY_ANNOTATION

def redeploy_affected_deployments(namespace, affected_secrets, logger, api_instance):
    try:
        apps_v1_api = AppsV1Api(api_instance.api_client)
        deployments = apps_v1_api.list_namespaced_deployment(namespace)
        for deployment in deployments.items:
            if should_redeploy(deployment, affected_secrets):
                patch_deployment_for_redeploy(deployment, namespace, apps_v1_api, logger)
    except ApiException as e:
        logger.error(f"Error listing deployments in namespace {namespace}: {e}")

def should_redeploy(deployment, affected_secrets):
    if not (deployment.metadata.annotations and REDEPLOY_ANNOTATION in deployment.metadata.annotations):
        return False

    deployment_secrets = extract_deployment_secrets(deployment)
    return any(secret in affected_secrets for secret in deployment_secrets)

def extract_deployment_secrets(deployment):
    secrets = []
    for container in deployment.spec.template.spec.containers:
        if container.env_from:
            for env_from in container.env_from:
                if env_from.secret_ref:
                    secrets.append(env_from.secret_ref.name)
    return secrets

def patch_deployment_for_redeploy(deployment, namespace, apps_v1_api, logger):
    try:
        timestamp = datetime.datetime.utcnow().isoformat()
        patch_body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "phase.autoredeploy.timestamp": timestamp
                        }
                    }
                }
            }
        }
        apps_v1_api.patch_namespaced_deployment(name=deployment.metadata.name, namespace=namespace, body=patch_body)
        logger.info(f"Triggered redeployment of {deployment.metadata.name} in namespace {namespace}")
    except ApiException as e:
        logger.error(f"Failed to patch deployment {deployment.metadata.name} in namespace {namespace}: {e}")