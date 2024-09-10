import kopf
import datetime
import kubernetes.client
from kubernetes.client.rest import ApiException
from kubernetes.client import CoreV1Api
from cmd.secrets.fetch import phase_secrets_fetch
from utils.secrets.write import create_secret
from utils.workload.deploy import redeploy_affected_deployments
from utils.const import PHASE_CLOUD_API_HOST

@kopf.timer('secrets.phase.dev', 'v1alpha1', 'phasesecrets', interval=60)
def sync_secrets(spec, name, namespace, logger, **kwargs):
    try:

        # Get Config
        api_instance = CoreV1Api()
        managed_secret_references = spec.get('managedSecretReferences', [])
        phase_host = spec.get('phaseHost', PHASE_CLOUD_API_HOST)
        phase_app = spec.get('phaseApp')
        phase_app_env = spec.get('phaseAppEnv', 'production')
        phase_app_env_path = spec.get('phaseAppEnvPath', '/')
        phase_app_env_tag = spec.get('phaseAppEnvTag')

        # If authentication serviceToken (Phase Service Token)
        service_token_secret_name = spec.get('authentication', {}).get('serviceToken', {}).get('serviceTokenSecretReference', {}).get('secretName', 'phase-service-token')
        api_response = api_instance.read_namespaced_secret(service_token_secret_name, namespace)
        service_token = base64.b64decode(api_response.data['token']).decode('utf-8')

        phase_secrets_dict = phase_secrets_fetch(
            phase_service_token=service_token,
            phase_service_host=phase_host,
            phase_app=phase_app,
            env_name=phase_app_env,
            tags=phase_app_env_tag,
            path=phase_app_env_path
        )

        secret_changed = False
        for secret_reference in managed_secret_references:
            secret_name = secret_reference['secretName']
            secret_namespace = secret_reference.get('secretNamespace', namespace)
            secret_type = secret_reference.get('secretType', 'Opaque')
            name_transformer = secret_reference.get('nameTransformer', 'upper_snake')
            processors = secret_reference.get('processors', {})

            processed_secrets = process_secrets(phase_secrets_dict, processors, secret_type, name_transformer)

            try:
                existing_secret = api_instance.read_namespaced_secret(name=secret_name, namespace=secret_namespace)
                if existing_secret.type != secret_type or existing_secret.data != processed_secrets:
                    api_instance.delete_namespaced_secret(name=secret_name, namespace=secret_namespace)
                    create_secret(api_instance, secret_name, secret_namespace, secret_type, processed_secrets, logger)
                    secret_changed = True
            except ApiException as e:
                if e.status == 404:
                    create_secret(api_instance, secret_name, secret_namespace, secret_type, processed_secrets, logger)
                    secret_changed = True
                else:
                    logger.error(f"Failed to update secret {secret_name} in namespace {secret_namespace}: {e}")

        if secret_changed:
            affected_secrets = [ref['secretName'] for ref in managed_secret_references]
            redeploy_affected_deployments(namespace, affected_secrets, logger, api_instance)

        logger.info(f"Secrets for PhaseSecret {name} have been successfully updated in namespace {namespace}")

    except ApiException as e:
        logger.error(f"Failed to fetch secrets for PhaseSecret {name} in namespace {namespace}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error when handling PhaseSecret {name} in namespace {namespace}: {e}")
