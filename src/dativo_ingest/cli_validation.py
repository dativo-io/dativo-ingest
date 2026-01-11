"""CLI command implementations for validation operations."""

import argparse
import sys
from pathlib import Path

from .config import JobConfig, AssetDefinition
from .logging import setup_logging
from .validator import ConnectorValidator
from .registry import ConnectorRegistry


def validate_config_command(args: argparse.Namespace) -> int:
    """Validate job configuration schema, connector references, and registry compatibility.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 2=failure)
    """
    logger = setup_logging(level="INFO", redact_secrets=True)
    
    logger.info(
        f"Validating job configuration: {args.path}",
        extra={"event_type": "validate_config_started"}
    )

    try:
        # 1. Load Job Config (Implicitly validates schema via pydantic/config.py)
        job_config = JobConfig.from_yaml(args.path)
        logger.info("Job configuration syntax is valid.")

        # 2. Validate Schema Presence
        job_config.validate_schema_presence()
        logger.info("Schema presence validated.")

        # 3. Validate Connector References & Registry Compatibility
        # Using ConnectorValidator for more robust checks including mode and engine
        validator = ConnectorValidator()
        validator.validate_job(job_config, mode="self_hosted") # defaulting to self_hosted for validation unless specified?
        # Maybe we should expose mode argument in validate config too? 
        # The requirements didn't specify, but it's good practice. 
        # The validator uses "self_hosted" by default if not passed.
        
        logger.info("Connector references and registry compatibility validated.")
        
        logger.info(
            "Configuration validation successful.",
            extra={"event_type": "validate_config_success"}
        )
        return 0

    except (SystemExit, ValueError) as e:
        logger.error(
            f"Configuration validation failed: {e}",
            extra={"event_type": "validate_config_failed"}
        )
        print(f"ERROR: Configuration validation failed: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        logger.error(
            f"Unexpected error during validation: {e}",
            extra={"event_type": "validate_config_error"},
            exc_info=True
        )
        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        return 2


def validate_asset_command(args: argparse.Namespace) -> int:
    """Validate asset definition against ODCS + Dativo extensions.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 2=failure)
    """
    logger = setup_logging(level="INFO", redact_secrets=True)
    
    logger.info(
        f"Validating asset definition: {args.path}",
        extra={"event_type": "validate_asset_started"}
    )

    try:
        # Load Asset Definition (Implicitly validates structure via AssetDefinition.from_yaml)
        # This checks against the Pydantic model which represents ODCS + Dativo extensions
        asset_config = AssetDefinition.from_yaml(args.path)
        
        logger.info(f"Asset definition syntax is valid: {asset_config.name}")
        
        # Additional validations if needed (e.g. unique field names, valid types)
        field_names = set()
        for field in asset_config.schema:
             if field["name"] in field_names:
                 raise ValueError(f"Duplicate field name: {field['name']}")
             field_names.add(field["name"])
        
        logger.info(
            "Asset definition validation successful.",
            extra={"event_type": "validate_asset_success"}
        )
        return 0

    except (SystemExit, ValueError) as e:
        logger.error(
            f"Asset validation failed: {e}",
            extra={"event_type": "validate_asset_failed"}
        )
        print(f"ERROR: Asset validation failed: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        logger.error(
            f"Unexpected error during validation: {e}",
            extra={"event_type": "validate_asset_error"},
            exc_info=True
        )
        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        return 2
