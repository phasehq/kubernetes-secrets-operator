import kopf
import base64
import datetime
import kubernetes.client
from kubernetes.client.rest import ApiException
from kubernetes.client import AppsV1Api
from kubernetes.client import CoreV1Api
from src.cmd.secrets.fetch import phase_secrets_fetch

REDEPLOY_ANNOTATION = "secrets.phase.dev/redeploy"

@kopf.timer('secrets.phase.dev', 'v1alpha1', 'phasesecrets', interval=10)
def sync_secrets(spec, name, namespace, logger, **kwargs):
    try:
        api_instance = CoreV1Api()

        managed_secret_references = spec.get('managedSecretReferences', [])
        phase_host = spec.get('phaseHost', 'https://console.phase.dev')
        phase_app_env = spec.get('phaseAppEnv', 'production')
        service_token_secret_name = spec.get('authentication', {}).get('serviceToken', {}).get('serviceTokenSecretReference', {}).get('secretName', 'phase-service-token')
        
        api_response = api_instance.read_namespaced_secret(service_token_secret_name, namespace)
        service_token = base64.b64decode(api_response.data['token']).decode('utf-8')

        fetched_secrets_dict = phase_secrets_fetch(
            phase_service_token=service_token,
            phase_service_host=phase_host,
            env_name=phase_app_env
        )

        secret_changed = False
        for secret_reference in managed_secret_references:
            secret_name = secret_reference['secretName']
            secret_namespace = secret_reference.get('secretNamespace', namespace)
            secret_type = secret_reference.get('secretType', 'Opaque')
            name_transformer = secret_reference.get('nameTransformer', 'upper_snake')
            processors = secret_reference.get('processors', {})

            processed_secrets = process_secrets(fetched_secrets_dict, processors, secret_type, name_transformer)

            try:
                existing_secret = api_instance.read_namespaced_secret(name=secret_name, namespace=secret_namespace)
                if existing_secret.type != secret_type:
                    # Delete and recreate the secret if the type has changed
                    api_instance.delete_namespaced_secret(name=secret_name, namespace=secret_namespace)
                    logger.info(f"Deleted existing secret {secret_name} in namespace {secret_namespace} due to type change.")
                    create_secret(api_instance, secret_name, secret_namespace, secret_type, processed_secrets)
                elif existing_secret.data != processed_secrets:
                    # Update the secret if the data has changed
                    api_instance.replace_namespaced_secret(
                        name=secret_name,
                        namespace=secret_namespace,
                        body=kubernetes.client.V1Secret(
                            metadata=kubernetes.client.V1ObjectMeta(name=secret_name),
                            type=secret_type,
                            data=processed_secrets
                        )
                    )
                    logger.info(f"Updated secret {secret_name} in namespace {secret_namespace}")
                secret_changed = True
            except ApiException as e:
                if e.status == 404:
                    create_secret(api_instance, secret_name, secret_namespace, secret_type, processed_secrets, logger)
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

def process_secrets(fetched_secrets, processors, secret_type):
    processed_secrets = {}
    for key, value in fetched_secrets.items():
        processor_info = processors.get(key, {})
        processor_type = processor_info.get('type', 'plain')
        as_name = processor_info.get('asName', key)

        if processor_type == 'plain':
            processed_value = base64.b64encode(value.encode()).decode()
        elif processor_type == 'base64':
            processed_value = value
        else:
            processed_value = value  # Default to the original value if no matching processor

        processed_secrets[as_name] = processed_value

    return processed_secrets

def create_secret(api_instance, secret_name, secret_namespace, secret_type, secret_data, logger):
    try:
        api_instance.create_namespaced_secret(
            namespace=secret_namespace,
            body=kubernetes.client.V1Secret(
                metadata=kubernetes.client.V1ObjectMeta(name=secret_name),
                type=secret_type,
                data=secret_data
            )
        )
        logger.info(f"Created secret {secret_name} in namespace {secret_namespace}")
    except ApiException as e:
        logger.error(f"Failed to create secret {secret_name} in namespace {secret_namespace}: {e}")

def transform_name(secret_key, format):
    """
    Transforms a secret key from UPPER_SNAKE_CASE to the specified format.

    Args:
        secret_key (str): The secret key to transform.
        format (str): The target format ('camel', 'upper-camel', 'lower-snake', 'tf-var', 'dotnet-env', 'lower-kebab').

    Returns:
        str: The transformed secret key.
    """
    words = secret_key.lower().split('_')
    
    if format == 'camel':
        return words[0] + ''.join(word.capitalize() for word in words[1:])
    elif format == 'upper-camel':
        return ''.join(word.capitalize() for word in words)
    elif format == 'lower-snake':
        return '_'.join(words)
    elif format == 'tf-var':
        return 'TF_VAR_' + '_'.join(words)
    elif format == 'dotnet-env':
        return '__'.join(word.capitalize() for word in words)
    elif format == 'lower-kebab':
        return '-'.join(words)
    else:
        return secret_key  # Default: return the key as is if format is unknown
