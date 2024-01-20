import sys
import re
import base64
import json
import yaml
from src.utils.phase_io import Phase
from src.utils.const import cross_env_pattern, local_ref_pattern
from src.utils.misc import transform_name, process_secret

def phase_secrets_fetch(phase_service_token=None, phase_service_host=None, env_name=None, phase_app=None, keys=None, tags=None, secret_format=None, name_transformer='upper_snake', secret_processor='b64'):
    """
    Fetch, decrypt, process and return secrets based on the provided environment, keys, tags, and format.
    """

    phase = Phase(init=False, pss=phase_service_token, host=phase_service_host)

    try:
        secrets = phase.get(env_name=env_name, keys=keys, tag=tags, app_name=phase_app)
    except ValueError as e:
        print(f"Failed to fetch secrets: {e}")
        sys.exit(1)

    secrets_dict = {}
    for secret in secrets:
        transformed_name = transform_name(secret["key"], name_transformer)
        processed_secret = process_secret(secret["value"], secret_processor)
        secrets_dict[transformed_name] = processed_secret

    # Export based on selected format
    if secret_format == 'json':
        return json.dumps(secrets_dict)
    elif secret_format == 'dotnet-json':
        return json.dumps({key.replace('__', ':'): value for key, value in secrets_dict.items()})
    elif secret_format == 'env':
        return '\n'.join([f'{key}="{value}"' for key, value in secrets_dict.items()])
    elif secret_format == 'yaml':
        return yaml.dump(secrets_dict)
    elif secret_format == 'docker':
        return ' '.join([f'-e {key}="{value}"' for key, value in secrets_dict.items()])
    else:
        return secrets_dict
