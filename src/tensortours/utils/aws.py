"""AWS utility functions for TensorTours backend."""

import json
import logging
from typing import Optional, Union

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def get_secret(secret_name: str, client=None) -> str:
    """Retrieve a secret from AWS Secrets Manager.

    Args:
        secret_name: Name of the secret to retrieve
        client: Optional boto3 secrets client

    Returns:
        The secret string

    Raises:
        ClientError: If there's an error retrieving the secret
    """
    secrets_client = client or boto3.client("secretsmanager")
    secret_string = ""
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        if "SecretString" in response:
            secret_string = response["SecretString"]
    except ClientError as e:
        logger.exception(f"Error retrieving secret {secret_name}")
        raise e
    return secret_string


def parse_json_secret(secret: str):
    """Parse a JSON-formatted secret string.

    Args:
        secret: Secret string that might be JSON

    Returns:
        Dictionary of parsed secret or empty dict on error
    """
    try:
        return json.loads(secret)
    except json.JSONDecodeError:
        logger.warning("Failed to parse secret as JSON, returning as-is")
        return {}


def get_api_key_from_secret(secret_name: str, key_name: str) -> Optional[str]:
    """Get an API key from a secret, supporting both direct and JSON formats.

    Args:
        secret_name: Name of the secret in Secrets Manager
        key_name: Name of the key in the JSON object (if applicable)

    Returns:
        API key string or None if not found
    """
    secret = get_secret(secret_name)
    if not secret:
        return None

    try:
        secret_dict = json.loads(secret)
        # Get the value from the dict or use the original secret as fallback
        value = secret_dict.get(key_name, secret)
        # Ensure we're returning a string or None
        return str(value) if value is not None else None
    except json.JSONDecodeError:
        # Return the original secret as a string if it's not None
        return str(secret) if secret is not None else None


def check_if_file_exists(bucket_name: str, key: str, s3_client=None) -> bool:
    """Check if a file exists in an S3 bucket.

    Args:
        bucket_name: S3 bucket name
        key: S3 object key
        s3_client: Optional boto3 S3 client

    Returns:
        True if file exists, False otherwise
    """
    client = s3_client or boto3.client("s3")

    try:
        client.head_object(Bucket=bucket_name, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        else:
            logger.exception(f"Error checking if file exists: {key}")
            return False


def upload_to_s3(
    bucket_name: str,
    key: str,
    data: Union[str, bytes],
    content_type: str = "application/json",
    binary: bool = False,
    s3_client=None,
) -> bool:
    """Upload data to an S3 bucket.

    Args:
        bucket_name: S3 bucket name
        key: S3 object key
        data: Data to upload (string or bytes)
        content_type: MIME type of the data
        binary: If True, data is treated as binary
        s3_client: Optional boto3 S3 client

    Returns:
        True if upload succeeded, False otherwise
    """
    client = s3_client or boto3.client("s3")

    try:
        body = data if binary else data if isinstance(data, bytes) else data.encode("utf-8")
        client.put_object(Bucket=bucket_name, Key=key, Body=body, ContentType=content_type)
        return True
    except Exception:
        logger.exception(f"Error uploading to S3: {key}")
        return False
