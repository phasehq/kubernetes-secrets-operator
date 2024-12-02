import os

def get_service_account_jwt() -> str:
    """
    Retrieve the JWT token from the current service account in a Kubernetes environment.
    
    This function reads the JWT token from the filesystem, which is the standard
    location in a Kubernetes pod.
    
    Returns:
        str: The service account JWT token
    
    Raises:
        Exception: If the token cannot be retrieved from the filesystem
    """
    token_path = '/var/run/secrets/kubernetes.io/serviceaccount/token'
    
    if os.path.exists(token_path):
        with open(token_path, 'r') as token_file:
            return token_file.read().strip()
    
    raise Exception("Service account JWT token not found. Are you running inside a Kubernetes pod?")
