import kubernetes
from kubernetes.client.rest import ApiException
import logging

def create_secret(api_instance, secret_name, secret_namespace, secret_type, secret_data, logger):
    try:
        response = api_instance.create_namespaced_secret(
            namespace=secret_namespace,
            body=kubernetes.client.V1Secret(
                metadata=kubernetes.client.V1ObjectMeta(name=secret_name),
                type=secret_type,
                data=secret_data
            )
        )
        if response:
            logger.info(f"Created secret {secret_name} in namespace {secret_namespace}")
    except ApiException as e:
        logger.error(f"Failed to create secret {secret_name} in namespace {secret_namespace}: {e}")