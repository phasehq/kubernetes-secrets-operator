import sys
import logging
from utils.phase_io import Phase
from utils.secret_referencing import resolve_all_secrets

# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

def phase_secrets_fetch(phase_service_token=None, phase_service_host=None, env_name=None, phase_app=None, phase_app_id=None, keys=None, tags=None, path='/'):
    """
    Fetch and return secrets based on the provided environment, keys, and tags.
    """
    
    phase = Phase(init=False, pss=phase_service_token, host=phase_service_host)

    try:
        all_secrets = phase.get(env_name=env_name, app_name=phase_app, app_id=phase_app_id, tag=tags, path=path)
        resolved_secrets = []
        for secret in all_secrets:
            try:
                # Ensure we use the correct environment name for each secret
                current_env_name = secret['environment']
                current_application_name = secret['application']

                # Attempt to resolve secret references in the value
                resolved_value = resolve_all_secrets(value=secret["value"], all_secrets=all_secrets, current_application_name=current_application_name, current_env_name=current_env_name, phase=phase)
                resolved_secrets.append({
                    **secret,
                    "value": resolved_value  # Replace original value with resolved value
                })

            except ValueError as e:
                logger.error(f"Failed to fetch secrets: {e}")
                sys.exit(1)

        # Create a dictionary with keys and resolved values outside the loop
        all_secrets_dict = {secret["key"]: secret["value"] for secret in resolved_secrets}

    except Exception as e:
        logger.error(f"Failed to fetch secrets: {e}")
        sys.exit(1)

    # Return secrets as a dictionary, ensure this is outside the try-except block
    return all_secrets_dict
