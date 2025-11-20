"""Native Stripe extractor using stripe Python SDK."""

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ..config import SourceConfig
from ..validator import IncrementalStateManager


class StripeExtractor:
    """Extracts data from Stripe API."""

    # Stripe rate limits: 7 requests per second, burst of 14
    RATE_LIMIT_RPS = 7
    RATE_LIMIT_BURST = 14

    def __init__(self, source_config: SourceConfig):
        """Initialize Stripe extractor.

        Args:
            source_config: Source configuration with objects and credentials
        """
        self.source_config = source_config
        self.engine_options = self._get_engine_options()
        self.api_key = self._get_api_key()
        self._init_stripe_client()
        self._last_request_time = 0.0
        self._request_count = 0
        self._window_start = time.time()

    def _get_engine_options(self) -> Dict[str, Any]:
        """Get engine options from source config.

        Returns:
            Dictionary of engine options
        """
        if self.source_config.engine:
            native_opts = self.source_config.engine.get("options", {}).get("native", {})
            if native_opts:
                return native_opts

        # Default options
        return {
            "batch_size": 100,  # Stripe default page size
            "max_retries": 5,
            "backoff_multiplier": 2.0,
            "max_backoff_seconds": 64,
        }

    def _get_api_key(self) -> str:
        """Get Stripe API key from credentials.

        Returns:
            Stripe API key

        Raises:
            ValueError: If API key is not found
        """
        # Check credentials dict
        if self.source_config.credentials:
            if isinstance(self.source_config.credentials, dict):
                # Try common key names
                for key in ["api_key", "STRIPE_API_KEY", "secret_key", "secret"]:
                    if key in self.source_config.credentials:
                        return str(self.source_config.credentials[key])

        # Check environment variable
        import os

        api_key = os.getenv("STRIPE_API_KEY")
        if api_key:
            return api_key

        raise ValueError(
            "Stripe API key not found. Provide it in credentials or set STRIPE_API_KEY environment variable."
        )

    def _init_stripe_client(self) -> None:
        """Initialize Stripe client with API key."""
        try:
            import stripe
        except ImportError:
            raise ImportError(
                "stripe is required for Stripe extraction. Install with: pip install stripe"
            )

        stripe.api_key = self.api_key

        # Set API version if specified
        if self.engine_options.get("api_version"):
            stripe.api_version = self.engine_options["api_version"]

        self.stripe = stripe

    def _rate_limit(self) -> None:
        """Implement rate limiting for Stripe API.

        Stripe allows 7 requests per second with a burst of 14.
        """
        current_time = time.time()

        # Reset window if more than 1 second has passed
        if current_time - self._window_start >= 1.0:
            self._request_count = 0
            self._window_start = current_time

        # Check if we've exceeded the rate limit
        if self._request_count >= self.RATE_LIMIT_RPS:
            # Calculate sleep time to stay within limits
            sleep_time = 1.0 - (current_time - self._window_start)
            if sleep_time > 0:
                time.sleep(sleep_time)
                self._request_count = 0
                self._window_start = time.time()

        self._request_count += 1

    def _handle_rate_limit_error(self, retry_count: int) -> bool:
        """Handle Stripe rate limit errors with exponential backoff.

        Args:
            retry_count: Current retry attempt number

        Returns:
            True if should retry, False otherwise
        """
        max_retries = self.engine_options.get("max_retries", 5)
        if retry_count >= max_retries:
            return False

        backoff_multiplier = self.engine_options.get("backoff_multiplier", 2.0)
        max_backoff = self.engine_options.get("max_backoff_seconds", 64)

        # Calculate exponential backoff
        sleep_time = min(backoff_multiplier**retry_count, max_backoff)
        time.sleep(sleep_time)
        return True

    def _stripe_object_to_dict(self, obj: Any) -> Dict[str, Any]:
        """Convert Stripe object to dictionary.

        Args:
            obj: Stripe object (StripeObject instance)

        Returns:
            Dictionary representation of the object
        """
        if hasattr(obj, "to_dict"):
            return obj.to_dict()

        # Fallback: convert manually
        result = {}
        for key, value in obj.__dict__.items():
            # Skip internal attributes
            if key.startswith("_"):
                continue

            # Handle nested Stripe objects
            if hasattr(value, "to_dict"):
                result[key] = value.to_dict()
            elif isinstance(value, list):
                result[key] = [
                    item.to_dict() if hasattr(item, "to_dict") else item
                    for item in value
                ]
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value

        return result

    def _get_objects_to_extract(self) -> List[str]:
        """Get list of Stripe objects to extract from source config.

        Returns:
            List of object names (e.g., ['customers', 'charges', 'invoices'])
        """
        # Check source config for objects
        if hasattr(self.source_config, "objects") and self.source_config.objects:
            return self.source_config.objects

        # Check source config dict if it's a dict
        if isinstance(self.source_config, dict) and "objects" in self.source_config:
            return self.source_config["objects"]

        # Default objects from connector recipe
        return ["customers", "charges", "invoices"]

    def _get_cursor_value(
        self, object_name: str, state_path: Optional[Path]
    ) -> Optional[int]:
        """Get cursor value (timestamp) from state for incremental sync.

        Args:
            object_name: Stripe object name (e.g., 'customers')
            state_path: Optional path to state file

        Returns:
            Unix timestamp or None
        """
        if not state_path:
            return None

        state_data = IncrementalStateManager.read_state(state_path)
        state_key = f"{object_name}.created"

        if state_key in state_data:
            last_value = state_data[state_key].get("last_value")
            if last_value:
                # Convert ISO format or timestamp to Unix timestamp
                if isinstance(last_value, str):
                    try:
                        dt = datetime.fromisoformat(last_value.replace("Z", "+00:00"))
                        return int(dt.timestamp())
                    except (ValueError, AttributeError):
                        # Try parsing as Unix timestamp string
                        try:
                            return int(float(last_value))
                        except (ValueError, TypeError):
                            return None
                elif isinstance(last_value, (int, float)):
                    return int(last_value)

        return None

    def _extract_object(
        self,
        object_name: str,
        cursor_value: Optional[int] = None,
        lookback_days: int = 0,
        state_path: Optional[Path] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract a single Stripe object type.

        Args:
            object_name: Stripe object name (e.g., 'customers', 'charges')
            cursor_value: Optional Unix timestamp for incremental sync
            lookback_days: Number of days to look back if no cursor value
            state_path: Optional path to state file

        Yields:
            Batches of records as dictionaries
        """
        # Map object names to Stripe API classes
        object_map = {
            "customers": self.stripe.Customer,
            "charges": self.stripe.Charge,
            "invoices": self.stripe.Invoice,
            "subscriptions": self.stripe.Subscription,
            "payment_intents": self.stripe.PaymentIntent,
            "products": self.stripe.Product,
            "prices": self.stripe.Price,
        }

        if object_name not in object_map:
            raise ValueError(f"Unsupported Stripe object: {object_name}")

        stripe_class = object_map[object_name]
        batch_size = self.engine_options.get("batch_size", 100)

        # Build list parameters
        list_params: Dict[str, Any] = {
            "limit": batch_size,
        }

        # Add incremental sync filter
        if cursor_value is not None:
            # Use created timestamp (Unix timestamp)
            list_params["created"] = {"gte": cursor_value}
        elif lookback_days > 0:
            # Calculate lookback timestamp
            lookback_timestamp = int(
                (datetime.now() - timedelta(days=lookback_days)).timestamp()
            )
            list_params["created"] = {"gte": lookback_timestamp}

        # Track last cursor value for state update
        last_cursor_value = None
        has_more = True
        starting_after = None
        retry_count = 0

        while has_more:
            # Apply rate limiting
            self._rate_limit()

            # Build request params (copy base params and add pagination)
            request_params = list_params.copy()
            if starting_after:
                request_params["starting_after"] = starting_after

            try:
                # Make API call
                response = stripe_class.list(**request_params)

                # Reset retry count on success
                retry_count = 0

                # Convert Stripe objects to dictionaries
                batch = []
                for obj in response.data:
                    record = self._stripe_object_to_dict(obj)
                    batch.append(record)

                    # Track last cursor value (created timestamp)
                    if "created" in record:
                        created_ts = record["created"]
                        if isinstance(created_ts, int):
                            if (
                                last_cursor_value is None
                                or created_ts > last_cursor_value
                            ):
                                last_cursor_value = created_ts

                if batch:
                    yield batch

                # Check if there are more pages
                has_more = response.has_more
                if has_more and response.data:
                    # Use the last object's ID for pagination
                    starting_after = response.data[-1].id
                else:
                    has_more = False

            except self.stripe.error.RateLimitError:
                # Handle rate limit error
                if not self._handle_rate_limit_error(retry_count):
                    raise
                retry_count += 1
                # Continue loop to retry

            except self.stripe.error.APIConnectionError:
                # Handle connection errors
                if not self._handle_rate_limit_error(retry_count):
                    raise
                retry_count += 1
                # Continue loop to retry

            except self.stripe.error.StripeError as e:
                # Other Stripe errors - don't retry
                raise RuntimeError(f"Stripe API error: {str(e)}") from e

        # Update state after successful processing
        if state_path and last_cursor_value is not None:
            state_key = f"{object_name}.created"
            state_data = IncrementalStateManager.read_state(state_path)
            if state_key not in state_data:
                state_data[state_key] = {}
            state_data[state_key]["last_value"] = last_cursor_value
            state_data[state_key]["updated_at"] = datetime.now().isoformat()
            IncrementalStateManager.write_state(state_path, state_data)

    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from Stripe API.

        Args:
            state_manager: Optional incremental state manager (not used for Stripe)

        Yields:
            Batches of records as dictionaries
        """
        # Get objects to extract
        objects = self._get_objects_to_extract()
        if not objects:
            raise ValueError("Stripe source requires 'objects' configuration")

        # Get incremental configuration
        incremental = self.source_config.incremental or {}
        strategy = incremental.get("strategy", "created")
        lookback_days = incremental.get("lookback_days", 0)
        state_path_str = incremental.get("state_path", "")
        state_path = Path(state_path_str) if state_path_str else None

        # Process each object
        for object_name in objects:
            # Get cursor value from state
            cursor_value = self._get_cursor_value(object_name, state_path)

            # Extract object data
            for batch in self._extract_object(
                object_name=object_name,
                cursor_value=cursor_value,
                lookback_days=lookback_days,
                state_path=state_path,
            ):
                yield batch
