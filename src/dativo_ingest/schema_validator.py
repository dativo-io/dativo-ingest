"""Schema validation engine for data records against asset definitions."""

import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from .config import AssetDefinition


class ValidationError:
    """Represents a validation error for a single record."""

    def __init__(
        self,
        record_index: int,
        field_name: str,
        error_type: str,
        message: str,
        value: Any = None,
    ):
        """Initialize validation error.

        Args:
            record_index: Index of the record in the batch
            field_name: Name of the field with the error
            error_type: Type of error (missing_required, type_mismatch, etc.)
            message: Human-readable error message
            value: The value that caused the error (if any)
        """
        self.record_index = record_index
        self.field_name = field_name
        self.error_type = error_type
        self.message = message
        self.value = value

    def __repr__(self) -> str:
        return f"ValidationError(record={self.record_index}, field={self.field_name}, type={self.error_type}, message={self.message})"


class SchemaValidator:
    """Validates data records against asset schema definitions."""

    def __init__(
        self,
        asset_definition: AssetDefinition,
        validation_mode: str = "strict",
    ):
        """Initialize schema validator.

        Args:
            asset_definition: Asset definition containing schema
            validation_mode: Validation mode - 'strict' (fail on errors) or 'warn' (log and continue)
        """
        self.asset_definition = asset_definition
        self.validation_mode = validation_mode
        self.schema_fields = {field["name"]: field for field in asset_definition.schema}
        self.errors: List[ValidationError] = []

    def validate_record(
        self, record: Dict[str, Any], record_index: int = 0
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Validate and coerce a single record.

        Args:
            record: Record dictionary to validate
            record_index: Index of record in batch (for error reporting)

        Returns:
            Tuple of (is_valid, coerced_record)
            - is_valid: True if record passes validation
            - coerced_record: Record with type-coerced values (None if invalid in strict mode)
        """
        errors: List[ValidationError] = []
        coerced_record: Dict[str, Any] = {}

        # Check required fields
        for field_name, field_def in self.schema_fields.items():
            is_required = field_def.get("required", False)
            field_type = field_def.get("type", "string")

            if field_name not in record or record[field_name] is None:
                if is_required:
                    errors.append(
                        ValidationError(
                            record_index=record_index,
                            field_name=field_name,
                            error_type="missing_required",
                            message=f"Required field '{field_name}' is missing",
                        )
                    )
                    if self.validation_mode == "strict":
                        continue  # Skip this field in strict mode
                # Optional field is missing - skip it
                continue

            value = record[field_name]

            # Coerce and validate type
            try:
                coerced_value = self._coerce_type(value, field_type, field_name)
                coerced_record[field_name] = coerced_value
            except (ValueError, TypeError) as e:
                errors.append(
                    ValidationError(
                        record_index=record_index,
                        field_name=field_name,
                        error_type="type_mismatch",
                        message=f"Field '{field_name}' type mismatch: {str(e)}",
                        value=value,
                    )
                )
                if self.validation_mode == "strict":
                    # In strict mode, don't include invalid fields
                    continue
                # In warn mode, include original value
                coerced_record[field_name] = value

        # Check for extra fields (fields in record but not in schema)
        # We'll allow extra fields but could log them if needed

        # Store errors
        self.errors.extend(errors)

        # Determine if record is valid
        is_valid = len(errors) == 0 or self.validation_mode == "warn"

        if not is_valid:
            return False, None

        return True, coerced_record

    def validate_batch(
        self, records: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[ValidationError]]:
        """Validate a batch of records.

        Args:
            records: List of record dictionaries to validate

        Returns:
            Tuple of (valid_records, errors)
            - valid_records: List of validated and coerced records
            - errors: List of validation errors
        """
        self.errors = []
        valid_records: List[Dict[str, Any]] = []

        for idx, record in enumerate(records):
            is_valid, coerced_record = self.validate_record(record, idx)

            if is_valid and coerced_record is not None:
                valid_records.append(coerced_record)
            elif self.validation_mode == "warn":
                # In warn mode, include record even with errors (with original values)
                valid_records.append(record)

        return valid_records, self.errors

    def _coerce_type(self, value: Any, target_type: str, field_name: str) -> Any:
        """Coerce value to target type.

        Args:
            value: Value to coerce
            target_type: Target type (string, integer, timestamp, etc.)
            field_name: Name of field (for error messages)

        Returns:
            Coerced value

        Raises:
            ValueError: If coercion fails
            TypeError: If value type is incompatible
        """
        if value is None:
            return None

        # Handle string type
        if target_type == "string":
            return str(value)

        # Handle integer type
        if target_type == "integer":
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                # Try to parse as int
                try:
                    return int(value)
                except ValueError:
                    raise ValueError(f"Cannot convert '{value}' to integer") from None
            if isinstance(value, float):
                # Convert float to int (truncate)
                return int(value)
            raise TypeError(f"Cannot convert {type(value).__name__} to integer")

        # Handle float/double type
        if target_type in ["float", "double"]:
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    raise ValueError(f"Cannot convert '{value}' to float") from None
            raise TypeError(f"Cannot convert {type(value).__name__} to float")

        # Handle boolean type
        if target_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lower = value.lower()
                if lower in ["true", "1", "yes", "on"]:
                    return True
                if lower in ["false", "0", "no", "off"]:
                    return False
                raise ValueError(f"Cannot convert '{value}' to boolean") from None
            if isinstance(value, (int, float)):
                return bool(value)
            raise TypeError(f"Cannot convert {type(value).__name__} to boolean")

        # Handle timestamp/date types
        if target_type in ["timestamp", "datetime", "date"]:
            if isinstance(value, datetime.datetime):
                return value
            if isinstance(value, datetime.date):
                return datetime.datetime.combine(value, datetime.time.min)
            if isinstance(value, str):
                # Try common timestamp formats
                formats = [
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d",
                    "%Y-%m-%dT%H:%M:%S%z",
                ]
                for fmt in formats:
                    try:
                        return datetime.datetime.strptime(value, fmt)
                    except ValueError:
                        continue
                raise ValueError(f"Cannot parse timestamp '{value}'") from None
            raise TypeError(f"Cannot convert {type(value).__name__} to timestamp")

        # Default: return as-is (for unknown types or if already correct type)
        return value

    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of validation errors.

        Returns:
            Dictionary with error statistics
        """
        if not self.errors:
            return {
                "total_errors": 0,
                "errors_by_type": {},
                "errors_by_field": {},
            }

        errors_by_type: Dict[str, int] = {}
        errors_by_field: Dict[str, int] = {}

        for error in self.errors:
            errors_by_type[error.error_type] = (
                errors_by_type.get(error.error_type, 0) + 1
            )
            errors_by_field[error.field_name] = (
                errors_by_field.get(error.field_name, 0) + 1
            )

        return {
            "total_errors": len(self.errors),
            "errors_by_type": errors_by_type,
            "errors_by_field": errors_by_field,
            "errors": [
                {
                    "record_index": e.record_index,
                    "field": e.field_name,
                    "type": e.error_type,
                    "message": e.message,
                }
                for e in self.errors[:100]  # Limit to first 100 errors
            ],
        }
