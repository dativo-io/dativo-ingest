"""Infrastructure health checks for validating dependencies."""

import os
import socket
from typing import List, Optional
from urllib.parse import urlparse

import requests

from .config import JobConfig


def validate_required_ports(ports: List[int], host: str = "localhost") -> bool:
    """Validate that required ports are open.

    Args:
        ports: List of port numbers to check
        host: Hostname to check (default: localhost)

    Returns:
        True if all ports are accessible

    Raises:
        ValueError: If any port is not accessible
    """
    failed_ports = []
    for port in ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            if result != 0:
                failed_ports.append(port)
        except Exception:
            failed_ports.append(port)

    if failed_ports:
        raise ValueError(f"Ports not accessible on {host}: {failed_ports}")

    return True


def check_nessie_connectivity(uri: str, timeout: int = 5) -> bool:
    """Check Nessie catalog connectivity.

    Args:
        uri: Nessie catalog URI (e.g., "http://localhost:19120/api/v1")
        timeout: Request timeout in seconds (default: 5)

    Returns:
        True if Nessie is accessible

    Raises:
        ValueError: If Nessie is not accessible
    """
    try:
        # Try to reach Nessie API
        # Nessie typically has a /config endpoint
        parsed = urlparse(uri)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Try config endpoint
        config_url = f"{base_url}/api/v1/config"
        response = requests.get(config_url, timeout=timeout)
        if response.status_code in [200, 404]:  # 404 is OK, means server is responding
            return True
        
        # Try base API endpoint
        api_url = f"{base_url}/api/v1"
        response = requests.get(api_url, timeout=timeout)
        if response.status_code in [200, 404, 405]:  # 405 Method Not Allowed is OK
            return True
        
        raise ValueError(f"Nessie connectivity check failed: HTTP {response.status_code}")
    except requests.exceptions.ConnectionError as e:
        raise ValueError(f"Cannot connect to Nessie at {uri}: {e}")
    except requests.exceptions.Timeout:
        raise ValueError(f"Nessie connection timeout at {uri}")
    except Exception as e:
        raise ValueError(f"Nessie connectivity check failed: {e}")


def check_s3_connectivity(
    endpoint: str,
    access_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    region: Optional[str] = None,
    timeout: int = 5,
) -> bool:
    """Check S3/MinIO connectivity.

    Args:
        endpoint: S3 endpoint URL (e.g., "http://localhost:9000")
        access_key: S3 access key (optional for health check)
        secret_key: S3 secret key (optional for health check)
        timeout: Request timeout in seconds (default: 5)

    Returns:
        True if S3 is accessible

    Raises:
        ValueError: If S3 is not accessible
    """
    try:
        # Try to reach S3 endpoint
        parsed = urlparse(endpoint)
        health_url = f"{parsed.scheme}://{parsed.netloc}/minio/health/live"
        
        # Try MinIO health endpoint first
        try:
            response = requests.get(health_url, timeout=timeout)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        
        # Try basic connectivity to endpoint
        response = requests.get(endpoint, timeout=timeout)
        # Any response (even 403 Forbidden) means server is reachable
        return True
    except requests.exceptions.ConnectionError as e:
        raise ValueError(f"Cannot connect to S3 at {endpoint}: {e}")
    except requests.exceptions.Timeout:
        raise ValueError(f"S3 connection timeout at {endpoint}")
    except Exception as e:
        raise ValueError(f"S3 connectivity check failed: {e}")


def validate_infrastructure(job_config: JobConfig) -> None:
    """Validate infrastructure dependencies for a job configuration.

    Args:
        job_config: Job configuration to validate

    Raises:
        ValueError: If infrastructure validation fails
    """
    errors = []
    warnings = []

    # Get target configuration
    try:
        target_config = job_config.get_target()
    except Exception as e:
        errors.append(f"Failed to load target configuration: {e}")
        if errors:
            raise ValueError("; ".join(errors))
        return

    target_type = target_config.type

    # Validate Iceberg/Nessie connectivity
    if target_type == "iceberg":
        # Check for Nessie URI
        nessie_uri = os.getenv("NESSIE_URI")
        if not nessie_uri:
            errors.append("NESSIE_URI environment variable is not set")
        else:
            try:
                check_nessie_connectivity(nessie_uri)
            except ValueError as e:
                errors.append(f"Nessie connectivity failed: {e}")

        # Check for S3 credentials
        s3_endpoint = os.getenv("S3_ENDPOINT")
        if not s3_endpoint:
            errors.append("S3_ENDPOINT environment variable is not set")
        else:
            try:
                check_s3_connectivity(s3_endpoint)
            except ValueError as e:
                errors.append(f"S3 connectivity failed: {e}")

        # Check required ports (Nessie default: 19120, MinIO default: 9000)
        try:
            nessie_port = 19120
            if nessie_uri:
                parsed = urlparse(nessie_uri)
                if parsed.port:
                    nessie_port = parsed.port
            validate_required_ports([nessie_port])
        except ValueError as e:
            warnings.append(f"Nessie port check: {e}")

        try:
            s3_port = 9000
            if s3_endpoint:
                parsed = urlparse(s3_endpoint)
                if parsed.port:
                    s3_port = parsed.port
            validate_required_ports([s3_port])
        except ValueError as e:
            warnings.append(f"S3 port check: {e}")

    # Validate S3 target connectivity
    elif target_type == "s3":
        s3_endpoint = os.getenv("S3_ENDPOINT")
        if not s3_endpoint:
            errors.append("S3_ENDPOINT environment variable is not set")
        else:
            try:
                check_s3_connectivity(s3_endpoint)
            except ValueError as e:
                errors.append(f"S3 connectivity failed: {e}")

    # Log warnings (non-fatal)
    if warnings:
        import logging

        logger = logging.getLogger(__name__)
        for warning in warnings:
            logger.warning(
                f"Infrastructure warning: {warning}",
                extra={"event_type": "infrastructure_warning", "warning": warning},
            )

    # Raise errors (fatal)
    if errors:
        raise ValueError("; ".join(errors))

