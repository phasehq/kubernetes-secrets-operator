import os
import base64
import platform
import subprocess
import json
from urllib.parse import urlparse
from typing import Union, List
from utils.const import __version__, PHASE_ENV_CONFIG, PHASE_CLOUD_API_HOST, PHASE_SECRETS_DIR, cross_env_pattern, local_ref_pattern


def get_default_user_host() -> str:
    """
    Determine the Phase host based on the available environment variables or the local configuration file.
    
    The function operates in the following order of preference:
    1. If the `PHASE_SERVICE_TOKEN` environment variable is available:
        a. Returns the value of the `PHASE_HOST` environment variable if set.
        b. If `PHASE_HOST` is not set, returns the default `PHASE_CLOUD_API_HOST`.
    2. If the `PHASE_SERVICE_TOKEN` environment variable is not available:
        a. Reads the local `config.json` file to retrieve the host for the default user.

    Parameters:
        None

    Returns:
        str: The Phase host, determined based on the environment variables or local configuration.

    Raises:
        ValueError: 
            - If the `config.json` file does not exist and the `PHASE_SERVICE_TOKEN` environment variable is not set.
            - If the default user's ID from the `config.json` does not correspond to any user entry in the file.

    Examples:
        >>> get_default_user_host()
        'https://console.phase.dev'  # This is just an example and the returned value might be different based on the actual environment and config.
    """

    # If PHASE_SERVICE_TOKEN is available
    if os.environ.get('PHASE_SERVICE_TOKEN'):
        return os.environ.get('PHASE_HOST', PHASE_CLOUD_API_HOST)

    config_file_path = os.path.join(PHASE_SECRETS_DIR, 'config.json')
    
    # Check if config.json exists
    if not os.path.exists(config_file_path):
        raise ValueError("Config file not found and no PHASE_SERVICE_TOKEN environment variable set.")
    
    with open(config_file_path, 'r') as f:
        config_data = json.load(f)

    default_user_id = config_data.get("default-user")
    
    for user in config_data.get("phase-users", []):
        if user["id"] == default_user_id:
            return user["host"]

    raise ValueError(f"No user found in config.json with id: {default_user_id}.")


def get_default_user_id(all_ids=False) -> Union[str, List[str]]:
    """
    Fetch the default user's ID from the config file in PHASE_SECRETS_DIR.

    Parameters:
    - all_ids (bool): If set to True, returns a list of all user IDs. Otherwise, returns the default user's ID.

    Returns:
    - Union[str, List[str]]: The default user's ID, or a list of all user IDs if all_ids is True.

    Raises:
    - ValueError: If the config file is not found or if the default user's ID is missing.
    """
    config_file_path = os.path.join(PHASE_SECRETS_DIR, 'config.json')
    
    if not os.path.exists(config_file_path):
        raise ValueError("No config found in '~/.phase/secrets/config.json'. Please login with phase auth")
    
    with open(config_file_path, 'r') as f:
        config_data = json.load(f)

    if all_ids:
        return [user['id'] for user in config_data.get('phase-users', [])]
    else:
        return config_data.get("default-user")


def phase_get_context(user_data, app_name=None, app_id=None, env_name=None):
    """
    Get the context (ID, name, and publicKey) for a specified application and environment.
    
    Parameters:
    - user_data (dict): The user data from the API response.
    - app_name (str, optional): The name (or partial name) of the desired application.
    - env_name (str, optional): The name (or partial name) of the desired environment.
    - app_id (str, optional): The ID of the desired application.
    
    Returns:
    - tuple: A tuple containing the application's name, application's ID, environment's name, environment's ID, and publicKey.

    Raises:
    - ValueError: If no matching application or environment is found.
    """
    # 1. Set default environment name if not provided
    env_name = env_name or "Development"

    # 2. Find the application
    try:
        if app_id:
            application = next((app for app in user_data["apps"] if app["id"] == app_id), None)
            if not application:
                raise ValueError(f"No application found with the ID '{app_id}'.")
        elif app_name:
            matching_apps = [app for app in user_data["apps"] if app_name.lower() in app["name"].lower()]
            if not matching_apps:
                raise ValueError(f"🔍 No application found with the name '{app_name}'.")
            # Sort matching applications by the length of their names, shorter names are likely to be more specific matches
            matching_apps.sort(key=lambda app: len(app["name"]))
            application = matching_apps[0]
        else:
            raise ValueError("🤔 No application context provided. Please specify either 'app_name' or 'app_id'.")

        # 3. Find the environment
        environment = next((env for env in application["environment_keys"] if env_name.lower() in env["environment"]["name"].lower()), None)
        if not environment:
            raise ValueError(f"⚠️ Warning: The environment '{env_name}' either does not exist or you do not have access to it.")

        # 4. Return application name, application ID, environment name, environment ID, and public key
        return (
            application["name"], # Phase app name
            application["id"], # Phase app id 
            environment["environment"]["name"], # Phase app env name
            environment["environment"]["id"], # Phase app env id
            environment["identity_key"] # Public key
        )
    except StopIteration:
        raise ValueError("🔍 Application or environment not found.")


def normalize_tag(tag):
    """
    Normalize a tag by replacing underscores with spaces.

    Args:
        tag (str): The tag to normalize.

    Returns:
        str: The normalized tag.
    """
    return tag.replace('_', ' ').lower()


def tag_matches(secret_tags, user_tag):
    """
    Check if the user-provided tag partially matches any of the secret tags.

    Args:
        secret_tags (list): The list of tags associated with a secret.
        user_tag (str): The user-provided tag to match.

    Returns:
        bool: True if there's a partial match, False otherwise.
    """
    normalized_user_tag = normalize_tag(user_tag)
    for tag in secret_tags:
        normalized_secret_tag = normalize_tag(tag)
        if normalized_user_tag in normalized_secret_tag:
            return True
    return False


def get_user_agent():
    """
    Constructs a user agent string containing information about the CLI's version, 
    the operating system, its version, its architecture, and the local username with machine name.
    
    Returns:
        str: The constructed user agent string.
    """

    details = []
    
    # Get CLI version
    try:
        cli_version = f"phase-kubernetes-operator/{__version__}"
        details.append(cli_version)
    except:
        pass

    # Get OS and version
    try:
        os_type = platform.system()  # e.g., Windows, Linux, Darwin (for macOS)
        os_version = platform.release()
        details.append(f"{os_type} {os_version}")
    except:
        pass

    # Get architecture
    try:
        architecture = platform.machine()
        details.append(architecture)
    except:
        pass

    # Get username and hostname
    try:
        username = os.getlogin()
        hostname = platform.node()
        user_host_string = f"{username}@{hostname}"
        details.append(user_host_string)
    except:
        pass

    user_agent_str = ' '.join(details)
    return user_agent_str


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
