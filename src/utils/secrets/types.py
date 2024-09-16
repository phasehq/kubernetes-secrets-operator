import base64

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

