import kopf
from kubernetes import client
from kubernetes.client.rest import ApiException
import base64
from utils.auth.kubernetes import get_service_account_jwt
from utils.network import authenticate_with_phase_api
from internals.secrets.fetch import phase_secrets_fetch
from typing import Dict
from utils.const import PHASE_CLOUD_API_HOST
from utils.cache import get_cached_token, update_cached_token
from utils.secrets.types import process_secrets
from utils.secrets.write import create_secret
from utils.workload.deploy import redeploy_affected_deployments

def get_phase_service_token(auth_config: Dict, phase_host: str, namespace: str, logger) -> str:
    if 'serviceToken' in auth_config:
        # Use existing service token authentication without caching
        service_token_secret_name = auth_config['serviceToken']['serviceTokenSecretReference']['secretName']
        service_token_secret_namespace = auth_config['serviceToken']['serviceTokenSecretReference'].get('secretNamespace', namespace)
        api_instance = client.CoreV1Api()
        api_response = api_instance.read_namespaced_secret(service_token_secret_name, service_token_secret_namespace)
        return base64.b64decode(api_response.data['token']).decode('utf-8')
    
    elif 'kubernetesAuth' in auth_config:
        kubernetes_auth = auth_config['kubernetesAuth']
        service_account_id = kubernetes_auth['phaseServiceAccountId']
        
        # Check for cached token
        cached_token = get_cached_token(service_account_id)
        if cached_token:
            return cached_token['token']

        # For testing TODO: remove later
        phase_host_test="https://psychology-jvc-pat-easily.trycloudflare.com"
        
        # If no valid cached token, authenticate
        jwt_token = get_service_account_jwt()
        auth_response = authenticate_with_phase_api(
            host=phase_host_test,
            auth_token=jwt_token,
            service_account_id=service_account_id,
            auth_type="kubernetes"
        )
        
        if not auth_response or 'token' not in auth_response:
            raise Exception("Failed to authenticate with Phase API")
        
        # Cache the new token
        update_cached_token(service_account_id, auth_response)
        
        logger.info(f"Refreshed Phase service token for service account {service_account_id}")
        return auth_response['token']
    else:
        raise Exception("No valid authentication method found in the spec")

@kopf.timer('secrets.phase.dev', 'v1alpha1', 'phasesecrets', interval=10)
def sync_secrets(spec, name, namespace, logger, **kwargs):
    try:
        # Get Config
        api_instance = client.CoreV1Api()
        managed_secret_references = spec.get('managedSecretReferences', [])
        phase_host = spec.get('phaseHost', PHASE_CLOUD_API_HOST)
        phase_app = spec.get('phaseApp')
        phase_app_env = spec.get('phaseAppEnv', 'production')
        phase_app_env_path = spec.get('phaseAppEnvPath', '/')
        phase_app_env_tag = spec.get('phaseAppEnvTag')

        # Get Phase service token
        auth_config = spec.get('authentication', {})
        phase_service_token = get_phase_service_token(auth_config, phase_host, namespace, logger)

        # Fetch secrets from Phase
        phase_secrets_dict = phase_secrets_fetch(
            phase_service_token=phase_service_token,
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
