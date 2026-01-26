import kopf
import base64
import datetime
import kubernetes.client
from kubernetes.client.rest import ApiException
from kubernetes.client import AppsV1Api
from kubernetes.client import CoreV1Api
from cmd.secrets.fetch import phase_secrets_fetch
from utils.const import REDEPLOY_ANNOTATION
from utils.sync_state_meta import sync_cache
from utils.phase_io import Phase
from utils.misc import phase_get_context
from dateutil import parser


def merge_secret_metadata(secret_reference, secret_name, secret_namespace, phase_secret_name, logger):
    """
    Merge user-defined metadata from CR template with operator-managed metadata.
    
    Follows CNCF best practices and KEP-1623 for recommended labels.
    - Operator-managed labels are always present and cannot be overridden
    - Reserved namespace 'secrets.phase.dev/*' is protected
    - User-defined labels and annotations are merged additively
    
    Args:
        secret_reference: Dict containing the managedSecretReference from CR
        secret_name: Name of the managed secret
        secret_namespace: Namespace of the managed secret
        phase_secret_name: Name of the PhaseSecret CR (owner)
        logger: Logger instance for warnings
        
    Returns:
        Tuple of (labels_dict, annotations_dict)
    """
    # Initialize with operator-managed labels (KEP-1623 recommended labels)
    labels = {
        'app.kubernetes.io/name': 'phase-secret',
        'app.kubernetes.io/instance': secret_name,
        'app.kubernetes.io/managed-by': 'phase-secrets-operator',
        'app.kubernetes.io/component': 'secret',
        'secrets.phase.dev/phasesecret': phase_secret_name,
        'secrets.phase.dev/managed': 'true'
    }
    
    # Initialize with operator-managed annotations
    annotations = {
        'secrets.phase.dev/last-sync': datetime.datetime.utcnow().isoformat() + 'Z'
    }
    
    # Extract user-defined metadata from template
    template_metadata = secret_reference.get('template', {}).get('metadata', {})
    user_labels = template_metadata.get('labels', {})
    user_annotations = template_metadata.get('annotations', {})
    
    # Merge user-defined labels (with validation)
    for key, value in user_labels.items():
        # Protect reserved namespace
        if key.startswith('secrets.phase.dev/'):
            logger.warning(
                f"Skipping user-defined label '{key}': reserved namespace 'secrets.phase.dev/*' "
                f"is managed by the operator"
            )
            continue
        
        # Protect KEP-1623 managed labels from override
        if key in ['app.kubernetes.io/managed-by', 'app.kubernetes.io/name']:
            logger.warning(
                f"Skipping user-defined label '{key}': this label is managed by the operator"
            )
            continue
        
        # Add user label
        labels[key] = str(value)
    
    # Merge user-defined annotations (no restrictions)
    for key, value in user_annotations.items():
        annotations[key] = str(value)
    
    return labels, annotations


def metadata_has_changed(existing_secret, expected_labels, expected_annotations):
    """
    Check if secret metadata needs to be updated.
    
    Args:
        existing_secret: V1Secret object from Kubernetes API
        expected_labels: Expected labels dict
        expected_annotations: Expected annotations dict
        
    Returns:
        Boolean indicating if metadata has changed
    """
    current_labels = existing_secret.metadata.labels or {}
    current_annotations = existing_secret.metadata.annotations or {}
    
    # Compare labels
    if current_labels != expected_labels:
        return True
    
    # Compare annotations
    if current_annotations != expected_annotations:
        return True
    
    return False


def create_secret_with_metadata(api_instance, secret_name, secret_namespace, secret_type, 
                                secret_data, labels, annotations, logger):
    """
    Create a Kubernetes Secret with metadata following CNCF best practices.
    
    Uses atomic create operation to ensure consistency.
    
    Args:
        api_instance: Kubernetes CoreV1Api instance
        secret_name: Name of the secret to create
        secret_namespace: Namespace for the secret
        secret_type: Type of Kubernetes secret (e.g., 'Opaque')
        secret_data: Base64 encoded secret data dictionary
        labels: Labels dictionary to apply
        annotations: Annotations dictionary to apply
        logger: Logger instance
    """
    try:
        metadata = kubernetes.client.V1ObjectMeta(
            name=secret_name,
            namespace=secret_namespace,
            labels=labels,
            annotations=annotations
        )
        
        secret_body = kubernetes.client.V1Secret(
            metadata=metadata,
            type=secret_type,
            data=secret_data
        )
        
        response = api_instance.create_namespaced_secret(
            namespace=secret_namespace,
            body=secret_body
        )
        
        if response:
            logger.info(
                f"Created secret '{secret_name}' in namespace '{secret_namespace}' "
                f"with {len(labels)} labels and {len(annotations)} annotations"
            )
    except ApiException as e:
        logger.error(f"Failed to create secret '{secret_name}' in namespace '{secret_namespace}': {e}")
        raise


def update_secret_with_metadata(api_instance, secret_name, secret_namespace, secret_type,
                                secret_data, labels, annotations, logger):
    """
    Update an existing Kubernetes Secret including data and metadata.
    
    Uses replace operation instead of patch for atomic updates.
    Follows Kubernetes best practices for resource updates.
    
    Args:
        api_instance: Kubernetes CoreV1Api instance
        secret_name: Name of the secret to update
        secret_namespace: Namespace of the secret
        secret_type: Type of Kubernetes secret
        secret_data: Base64 encoded secret data dictionary
        labels: Labels dictionary to apply
        annotations: Annotations dictionary to apply
        logger: Logger instance
    """
    try:
        metadata = kubernetes.client.V1ObjectMeta(
            name=secret_name,
            namespace=secret_namespace,
            labels=labels,
            annotations=annotations
        )
        
        secret_body = kubernetes.client.V1Secret(
            metadata=metadata,
            type=secret_type,
            data=secret_data
        )
        
        response = api_instance.replace_namespaced_secret(
            name=secret_name,
            namespace=secret_namespace,
            body=secret_body
        )
        
        if response:
            logger.info(
                f"Updated secret '{secret_name}' in namespace '{secret_namespace}' "
                f"with {len(labels)} labels and {len(annotations)} annotations"
            )
    except ApiException as e:
        logger.error(f"Failed to update secret '{secret_name}' in namespace '{secret_namespace}': {e}")
        raise


@kopf.timer('secrets.phase.dev', 'v1alpha1', 'phasesecrets', interval=60)
def phase_secret_sync(spec, name, namespace, logger, uid, **kwargs):
    try:
        api_instance = CoreV1Api()
        managed_secret_references = spec.get('managedSecretReferences', [])
        phase_host = spec.get('phaseHost', 'https://console.phase.dev')
        phase_app = spec.get('phaseApp')
        phase_app_env = spec.get('phaseAppEnv', 'production')
        phase_app_env_path = spec.get('phaseAppEnvPath', '/')
        phase_app_env_tag = spec.get('phaseAppEnvTag')
        service_token_secret_name = spec.get('authentication', {}).get('serviceToken', {}).get('serviceTokenSecretReference', {}).get('secretName', 'phase-service-token')
        service_token_secret_namespace = spec.get('authentication', {}).get('serviceToken', {}).get('serviceTokenSecretReference', {}).get('secretNamespace', namespace)

        api_response = api_instance.read_namespaced_secret(service_token_secret_name, service_token_secret_namespace)
        service_token = base64.b64decode(api_response.data['token']).decode('utf-8')

        # Initialize Phase client to fetch account access metadata and check timestamps
        try:
            phase = Phase(init=False, pss=service_token, host=phase_host)
            
            # Fetch account access metadata to get environment timestamps
            user_data = phase.init()
        except Exception as e:
            logger.error(f"Failed to fetch user data from Phase API: {e}")
            # On user data fetch failure, we can't determine if sync is needed, skip this cycle
            return
        
        # Parse the app and environment context
        try:
            app_name, app_id, env_name, env_id, public_key, updated_at_str = phase_get_context(
                user_data, app_name=phase_app, env_name=phase_app_env, include_timestamp=True
            )
            
            # Parse the updated_at timestamp
            target_env_updated_at = parser.parse(updated_at_str)
        except ValueError as e:
            logger.error(f"Failed to get app/environment context: {e}")
            return
        except Exception as e:
            logger.error(f"Failed to parse timestamp for environment '{phase_app_env}': {e}")
            return
        
        # Check if we need to sync based on timestamp
        needs_sync = sync_cache.needs_sync(
            namespace=namespace,
            cr_name=name,
            current_timestamp=target_env_updated_at,
            cr_uid=uid
        )
        
        if not needs_sync:
            logger.info(f"Environment '{phase_app_env}' for app '{phase_app}' has not been updated. No sync needed.")
            return
        
        # Environment has been updated, fetch secrets
        logger.info(f"Environment '{phase_app_env}' has been updated, fetching secrets")
        
        try:
            # Fetch secrets from Phase API
            phase_secrets_dict = phase_secrets_fetch(
                phase_service_token=service_token,
                phase_service_host=phase_host,
                phase_app=phase_app,
                env_name=phase_app_env,
                tags=phase_app_env_tag,
                path=phase_app_env_path
            )
        except Exception as e:
            logger.error(f"Failed to fetch secrets from Phase API for app '{phase_app}' environment '{phase_app_env}': {e}")
            # Don't update cache on fetch failure, retry on next cycle
            return

        secret_changed = False
        for secret_reference in managed_secret_references:
            secret_name = secret_reference['secretName']
            secret_namespace = secret_reference.get('secretNamespace', namespace)
            secret_type = secret_reference.get('secretType', 'Opaque')
            name_transformer = secret_reference.get('nameTransformer', 'upper_snake')
            processors = secret_reference.get('processors', {})

            # Process secret data
            processed_secrets = process_secrets(phase_secrets_dict, processors, secret_type, name_transformer)
            
            # Merge metadata from template with operator-managed metadata
            labels, annotations = merge_secret_metadata(
                secret_reference, secret_name, secret_namespace, name, logger
            )

            try:
                # Check if secret exists
                existing_secret = api_instance.read_namespaced_secret(
                    name=secret_name, 
                    namespace=secret_namespace
                )
                
                # Check if data or metadata has changed
                data_changed = (
                    existing_secret.type != secret_type or 
                    existing_secret.data != processed_secrets
                )
                metadata_changed = metadata_has_changed(existing_secret, labels, annotations)
                
                if data_changed or metadata_changed:
                    # Update secret with new data and/or metadata
                    update_secret_with_metadata(
                        api_instance, secret_name, secret_namespace, secret_type,
                        processed_secrets, labels, annotations, logger
                    )
                    secret_changed = True
                    
                    if data_changed and metadata_changed:
                        logger.info(f"Updated secret '{secret_name}' data and metadata")
                    elif data_changed:
                        logger.info(f"Updated secret '{secret_name}' data")
                    else:
                        logger.info(f"Updated secret '{secret_name}' metadata only")
                else:
                    logger.debug(f"Secret '{secret_name}' is up to date, no changes needed")
                    
            except ApiException as e:
                if e.status == 404:
                    # Secret doesn't exist, create it
                    create_secret_with_metadata(
                        api_instance, secret_name, secret_namespace, secret_type,
                        processed_secrets, labels, annotations, logger
                    )
                    secret_changed = True
                else:
                    logger.error(f"Failed to read secret '{secret_name}' in namespace '{secret_namespace}': {e}")

        if secret_changed:
            affected_secrets = [ref['secretName'] for ref in managed_secret_references]
            redeploy_affected_deployments(namespace, affected_secrets, logger, api_instance)

        # Update sync metadata timestamp
        sync_cache.update_sync_time(
            namespace=namespace,
            cr_name=name,
            timestamp=target_env_updated_at,
            cr_uid=uid
        )
        
        logger.info(f"Secrets for PhaseSecret '{name}' have been successfully synced in namespace '{namespace}'")

    except ApiException as e:
        logger.error(f"Failed to sync secrets for PhaseSecret '{name}' in namespace '{namespace}': {e}")
    except Exception as e:
        logger.error(f"Unexpected error when handling PhaseSecret '{name}' in namespace '{namespace}': {e}")


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


def process_secrets(fetched_secrets, processors, secret_type, name_transformer):
    processed_secrets = {}
    for key, value in fetched_secrets.items():
        processor_info = processors.get(key, {})
        processor_type = processor_info.get('type', 'plain')
        as_name = processor_info.get('asName', key)  # Use asName for mapping

        # Check and process the value based on the processor type
        if processor_type == 'base64':
            # Assume value is already base64 encoded; do not re-encode
            processed_value = value
        elif processor_type == 'plain':
            # Base64 encode the value
            processed_value = base64.b64encode(value.encode()).decode()
        else:
            # Default to plain processing if processor type is not recognized
            processed_value = base64.b64encode(value.encode()).decode()

        # Map the processed value to the asName
        processed_secrets[as_name] = processed_value

    return processed_secrets