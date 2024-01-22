import sys
from src.utils.phase_io import Phase

def phase_secrets_fetch(phase_service_token=None, phase_service_host=None, env_name=None, phase_app=None, keys=None, tags=None):
    """
    Fetch and return secrets based on the provided environment, keys, and tags.
    """

    phase = Phase(init=False, pss=phase_service_token, host=phase_service_host)

    try:
        secrets = phase.get(env_name=env_name, keys=keys, tag=tags, app_name=phase_app)
    except ValueError as e:
        print(f"Failed to fetch secrets: {e}")
        sys.exit(1)

    # Return secrets as a dictionary
    return {secret["key"]: secret["value"] for secret in secrets}
