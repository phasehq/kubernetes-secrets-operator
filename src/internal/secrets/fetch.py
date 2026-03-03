import logging
from utils.phase_io import Phase
from utils.secret_referencing import resolve_all_secrets, build_secrets_index

# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

def phase_secrets_fetch(
    phase_service_token=None,
    phase_service_host=None,
    env_name=None,
    phase_app=None,
    keys=None,
    tags=None,
    path='/',
    phase_client=None,
    user_data=None,
    resolved_context=None,
):
    """
    Fetch and return secrets based on the provided environment, keys, and tags.
    """
    
    phase = phase_client or Phase(init=False, pss=phase_service_token, host=phase_service_host)

    try:
        all_secrets = phase.get(
            env_name=env_name,
            app_name=phase_app,
            tag=tags,
            path=path,
            user_data=user_data,
            resolved_context=resolved_context,
        )
        secrets_dict = build_secrets_index(all_secrets)
        fetch_cache = {}
        resolved_secrets = []
        for secret in all_secrets:
            try:
                # Ensure we use the correct environment name for each secret
                current_env_name = secret['environment']
                current_application_name = secret['application']

                # Attempt to resolve secret references in the value
                resolved_value = resolve_all_secrets(
                    value=secret["value"],
                    all_secrets=all_secrets,
                    current_application_name=current_application_name,
                    current_env_name=current_env_name,
                    phase=phase,
                    secrets_dict=secrets_dict,
                    fetch_cache=fetch_cache,
                )
                resolved_secrets.append({
                    **secret,
                    "value": resolved_value  # Replace original value with resolved value
                })

            except ValueError as e:
                logger.error(f"Failed to fetch secrets: {e}")
                raise

        # Create a dictionary with keys and resolved values outside the loop
        all_secrets_dict = {secret["key"]: secret["value"] for secret in resolved_secrets}

    except Exception as e:
        logger.error(f"Failed to fetch secrets: {e}")
        raise

    # Return secrets as a dictionary, ensure this is outside the try-except block
    return all_secrets_dict
