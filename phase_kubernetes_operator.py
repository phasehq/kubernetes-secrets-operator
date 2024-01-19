import kopf
import base64
import datetime
import kubernetes.client
from kubernetes.client.rest import ApiException
from kubernetes.client import AppsV1Api
from src.cmd.secrets.export import phase_secrets_env_export

REDEPLOY_ANNOTATION = "phase.autoredeploy"

@kopf.timer('secrets.phase.dev', 'v1alpha1', 'phasesecrets', interval=60)
def sync_secrets(spec, name, namespace, logger, **kwargs):
    try:
        # Initialize Kubernetes client
        api_instance = kubernetes.client.CoreV1Api()

        # Extract information from the spec
        managed_secret_references = spec.get('managedSecretReferences', [])
        phase_host = spec.get('phaseHost', 'https://console.phase.dev')
        phase_app_env = spec.get('phaseAppEnv', 'production')
        service_token_secret_name = spec.get('authentication', {}).get('serviceToken', {}).get('serviceTokenSecretReference', {}).get('secretName', 'phase-service-token')

        # Fetch and process the Phase service token
        api_response = api_instance.read_namespaced_secret(service_token_secret_name, namespace)
        service_token = base64.b64decode(api_response.data['token']).decode('utf-8')

        # Fetch secrets from the Phase application
        fetched_secrets_dict = phase_secrets_env_export(
            phase_service_token=service_token,
            phase_service_host=phase_host,
            env_name=phase_app_env,
            export_type='k8'
        )

        secret_changed = False
        for secret_reference in managed_secret_references:
            secret_name = secret_reference['secretName']
            secret_namespace = secret_reference.get('secretNamespace', namespace)

            try:
                existing_secret = api_instance.read_namespaced_secret(name=secret_name, namespace=secret_namespace)
                if existing_secret.data != fetched_secrets_dict:
                    api_instance.replace_namespaced_secret(
                        name=secret_name,
                        namespace=secret_namespace,
                        body=kubernetes.client.V1Secret(
                            metadata=kubernetes.client.V1ObjectMeta(name=secret_name),
                            data=fetched_secrets_dict
                        )
                    )
                    logger.info(f"Updated secret {secret_name} in namespace {secret_namespace}")
                    secret_changed = True
            except ApiException as e:
                if e.status == 404:
                    api_instance.create_namespaced_secret(
                        namespace=secret_namespace,
                        body=kubernetes.client.V1Secret(
                            metadata=kubernetes.client.V1ObjectMeta(name=secret_name),
                            data=fetched_secrets_dict
                        )
                    )
                    logger.info(f"Created secret {secret_name} in namespace {secret_namespace}")
                    secret_changed = True
                else:
                    logger.error(f"Failed to update secret {secret_name} in namespace {secret_namespace}: {e}")

        if secret_changed:
            redeploy_affected_deployments(namespace, logger, api_instance)

        logger.info(f"Secrets for PhaseSecret {name} have been successfully updated in namespace {namespace}")

    except ApiException as e:
        logger.error(f"Failed to fetch secrets for PhaseSecret {name} in namespace {namespace}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error when handling PhaseSecret {name} in namespace {namespace}: {e}")

def redeploy_affected_deployments(namespace, logger, api_instance):
    try:
        apps_v1_api = AppsV1Api(api_instance.api_client)
        deployments = apps_v1_api.list_namespaced_deployment(namespace)
        for deployment in deployments.items:
            if deployment.metadata.annotations and REDEPLOY_ANNOTATION in deployment.metadata.annotations:
                patch_deployment_for_redeploy(deployment, namespace, apps_v1_api, logger)
    except ApiException as e:
        logger.error(f"Error listing deployments in namespace {namespace}: {e}")

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
