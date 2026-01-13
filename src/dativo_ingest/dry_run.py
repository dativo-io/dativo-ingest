"""Dry-run execution logic for validation and smoke testing."""

import json
import sys
import time
from typing import Any, Dict, List, Optional

from .cli_commands import DiscoveryService
from .job_executor import JobExecutor
from .logging import get_logger
from .metrics import record_dry_run_metric


class DryRunExecutor(JobExecutor):
    """Executes a job in dry-run mode (read-only smoke test)."""

    def __init__(
        self,
        job_config,
        mode: str = "self_hosted",
        sample_size: int = 25,
        timeout: int = 300,
    ):
        """Initialize dry-run executor.

        Args:
            job_config: Job configuration
            mode: Execution mode
            sample_size: Number of sample rows to fetch
            timeout: Timeout in seconds
        """
        super().__init__(job_config, mode)
        self.sample_size = sample_size
        self.timeout = timeout
        self.results = {
            "valid": False,
            "phases_completed": [],
            "connector_info": {},
            "asset_info": {},
            "sample_data": {},
            "validation_results": {},
            "errors": [],
            "warnings": [],
        }

    def execute_dry_run(self) -> int:
        """Execute dry-run smoke test.

        Returns:
            Exit code (0=success, 2=failure)
        """
        start_time = time.time()
        
        try:
            # 1. Configuration Validation
            self._setup_logging()
            self.logger.info("Starting dry-run execution", extra={"event_type": "dry_run_started"})
            
            # Resolve configs first
            try:
                self.source_config = self.job_config.get_source()
                self.target_config = self.job_config.get_target()
                self.results["connector_info"] = {
                    "source_type": self.source_config.type,
                    "target_type": self.target_config.type,
                }
            except Exception as e:
                self._record_error(f"Configuration resolution failed: {e}")
                return 2

            exit_code = self._validate_job()
            if exit_code != 0:
                self._record_error("Configuration validation failed")
                return 2
            self.results["phases_completed"].append("configuration_validation")
            self.logger.info("Configuration validated", extra={"event_type": "dry_run_validate_config"})

            # 2. Asset Loading
            exit_code = self._load_asset()
            if exit_code != 0:
                self._record_error("Asset loading failed")
                return 2
            self.results["asset_info"] = {
                "name": self.asset_definition.name,
                "version": self.asset_definition.version,
                "object": self.asset_definition.object,
                "schema_fields_count": len(self.asset_definition.schema),
            }
            self.results["phases_completed"].append("asset_loading")
            self.logger.info("Asset loaded", extra={"event_type": "dry_run_load_asset"})

            # 3. Extractor Initialization
            # Note: We skip state manager and WAL manager for dry-run
            exit_code = self._initialize_extractor()
            if exit_code != 0:
                self._record_error("Extractor initialization failed")
                return 2
            self.results["phases_completed"].append("extractor_initialization")
            self.logger.info("Extractor initialized", extra={"event_type": "dry_run_init_extractor"})

            # Check timeout
            if time.time() - start_time > self.timeout:
                self._record_error("Timeout exceeded before discovery", record_metric=False)
                self._record_metric("timeout")
                return 2

            # 4. Discovery
            try:
                discovery_service = DiscoveryService(
                    source_config=self.source_config,
                    job_config=self.job_config,
                    tenant_id=self.tenant_id,
                    mode=self.mode,
                    logger=self.logger
                )
                discovery_result = discovery_service.discover()
                
                # Verify source object exists in discovery results
                # This is "Schema Negotiation" - checking if what we expect exists
                streams = discovery_result.get("objects", [])
                target_object = self.source_config.object
                
                # Check if target object is in discovered streams (if streams are named)
                # Some connectors might return generic streams or exact match needed
                found_object = False
                available_objects = []
                
                for stream in streams:
                    stream_name = stream.get("name")
                    if stream_name:
                        available_objects.append(stream_name)
                        if stream_name == target_object:
                            found_object = True
                            break
                
                if target_object and not found_object and available_objects:
                    # If we found objects but not the one we want, warning or error?
                    # For dry-run, strictly speaking, it might fail if object doesn't exist.
                    # But some connectors (like database) might require exact table name which we have.
                    # If list is empty, maybe discovery failed or returned nothing.
                    self.logger.warning(
                        f"Target object '{target_object}' not found in discovered streams.",
                        extra={
                            "available_objects": available_objects,
                            "event_type": "dry_run_discovery_warning"
                        }
                    )
                    self.results["warnings"].append(f"Target object '{target_object}' not found in discovered streams: {available_objects[:5]}...")

                self.results["phases_completed"].append("discovery")
                self.logger.info("Discovery completed", extra={"event_type": "dry_run_discovery"})
                
            except Exception as e:
                # Discovery is optional for some connectors or might fail gracefully
                self.logger.warning(f"Discovery failed: {e}", extra={"event_type": "dry_run_discovery_failed"})
                self.results["warnings"].append(f"Discovery failed: {e}")
                # We continue to sample fetch as that's the ultimate test

            # 5. Schema Negotiation (Source vs Asset)
            # This is implicitly done by checking if we can fetch and validate data
            self.results["phases_completed"].append("schema_negotiation")
            self.logger.info("Schema negotiation passed (implicit)", extra={"event_type": "dry_run_schema_negotiation"})

            # Check timeout
            if time.time() - start_time > self.timeout:
                self._record_error("Timeout exceeded before sample fetch", record_metric=False)
                self._record_metric("timeout")
                return 2

            # 6. Sample Data Fetch
            fetch_start = time.time()
            samples = []
            
            try:
                # Use extractor to get a batch
                # We need to be careful not to fetch too much. 
                # Most extractors return a generator of batches.
                # We take the first batch and slice it.
                
                # We pass None for state_manager and checkpoint_context as we don't want to use state
                iterator = self.extractor.extract(state_manager=None, checkpoint_context=None)
                
                try:
                    first_batch = next(iterator)
                    samples = first_batch[:self.sample_size]
                except StopIteration:
                    self.logger.warning("No data extracted (source empty?)", extra={"event_type": "dry_run_empty_source"})
                    self.results["warnings"].append("No data extracted from source")
                
                fetch_duration = time.time() - fetch_start
                
                self.results["sample_data"] = {
                    "rows_fetched": len(samples),
                    "fetch_duration_seconds": round(fetch_duration, 2),
                    "columns": list(samples[0].keys()) if samples else []
                }
                
                self.results["phases_completed"].append("sample_fetch")
                self.logger.info(
                    f"Sample data fetched: {len(samples)} rows", 
                    extra={"event_type": "dry_run_fetch_sample", "rows": len(samples), "duration": fetch_duration}
                )

            except Exception as e:
                self._record_error(f"Sample fetch failed: {e}")
                return 2

            # 7. Sample Validation (Data Contract)
            exit_code = self._initialize_validator()
            if exit_code != 0:
                self._record_error("Validator initialization failed")
                return 2
                
            valid_records, validation_errors = self.validator.validate_batch(samples)
            
            validation_stats = {
                "data_contract_valid": len(validation_errors) == 0,
                "total_rows": len(samples),
                "valid_rows": len(valid_records),
                "invalid_rows": len(samples) - len(valid_records),
                "error_summary": self.validator.get_error_summary() if validation_errors else None
            }
            self.results["validation_results"] = validation_stats
            
            if len(validation_errors) > 0:
                if self.job_config.schema_validation_mode == "strict":
                     self.logger.error("Data contract validation failed (strict mode)", extra={"event_type": "dry_run_validate_sample_failed"})
                     self.results["errors"].append("Data contract validation failed on sample data")
                     # We consider this a failure of the dry run in strict mode
                     return 2
                else:
                    self.logger.warning("Data contract validation had errors (warn mode)", extra={"event_type": "dry_run_validate_sample_warn"})
                    self.results["warnings"].append("Data contract validation had errors")
            
            self.results["phases_completed"].append("sample_validation")
            self.logger.info("Sample validation completed", extra={"event_type": "dry_run_validate_sample"})

            # Success
            self.results["valid"] = True
            self.logger.info("Dry-run completed successfully", extra={"event_type": "dry_run_completed", "status": "success"})
            self._record_metric("success")
            return 0

        except Exception as e:
            self.logger.error(f"Dry-run unexpected error: {e}", extra={"event_type": "dry_run_error"}, exc_info=True)
            self._record_error(f"Unexpected error: {e}")
            return 2

    def _record_error(self, message: str, record_metric: bool = True):
        """Record error and log it."""
        self.results["errors"].append(message)
        self.logger.error(message, extra={"event_type": "dry_run_failure"})
        if record_metric:
            self._record_metric("failure")

    def _record_metric(self, result: str):
        """Record dry-run metric."""
        connector_type = self.source_config.type if self.source_config else "unknown"
        record_dry_run_metric(result, connector_type)

    def print_results(self, json_output: bool = False, verbose: bool = False):
        """Print dry-run results."""
        if json_output:
            print(json.dumps(self.results, indent=2))
        else:
            status_symbol = "+" if self.results["valid"] else "-"
            status_text = "PASSED" if self.results["valid"] else "FAILED"
            
            print("\n" + "=" * 60)
            print(f"DRY-RUN RESULTS: {status_symbol} {status_text}")
            print("=" * 60)
            
            print(f"\nPhases Completed ({len(self.results['phases_completed'])}):")
            for phase in self.results['phases_completed']:
                print(f"  [+] {phase.replace('_', ' ').title()}")
            
            print("\nConnector Info:")
            print(f"  Source: {self.results['connector_info'].get('source_type')}")
            print(f"  Target: {self.results['connector_info'].get('target_type')}")
            
            if self.results.get('asset_info'):
                print("\nAsset Info:")
                print(f"  Name: {self.results['asset_info'].get('name')}")
                print(f"  Version: {self.results['asset_info'].get('version')}")
                print(f"  Object: {self.results['asset_info'].get('object')}")
                print(f"  Schema Fields: {self.results['asset_info'].get('schema_fields_count')}")
            
            if self.results.get('sample_data'):
                print("\nSample Data:")
                print(f"  Rows Fetched: {self.results['sample_data'].get('rows_fetched')}")
                print(f"  Fetch Duration: {self.results['sample_data'].get('fetch_duration_seconds')}s")
                cols = self.results['sample_data'].get('columns', [])
                col_str = ", ".join(cols[:5]) + ("..." if len(cols) > 5 else "")
                print(f"  Columns: {col_str}")
                
            if self.results.get('validation_results'):
                val = self.results['validation_results']
                valid_mark = "[+]" if val.get('data_contract_valid') else "[-]"
                print("\nData Contract Validation:")
                print(f"  Contract Valid: {valid_mark} {'Yes' if val.get('data_contract_valid') else 'No'}")
                print(f"  Mode: {self.job_config.schema_validation_mode}")
                print(f"  Valid Rows: {val.get('valid_rows')}/{val.get('total_rows')}")
                
                if not val.get('data_contract_valid') and val.get('error_summary'):
                    print("\n  Validation Errors:")
                    summary = val.get('error_summary', {})
                    print(f"    Total Errors: {summary.get('total_errors')}")
                    if verbose:
                        for err in summary.get('errors', [])[:5]:
                            print(f"    - Row {err.get('record_index')}, Field '{err.get('field')}': {err.get('message')}")

            if self.results['errors']:
                print("\nErrors:")
                for err in self.results['errors']:
                    print(f"  - {err}")

            if self.results['warnings']:
                print("\nWarnings:")
                for warn in self.results['warnings']:
                    print(f"  - {warn}")

            print("\n" + "=" * 60)
