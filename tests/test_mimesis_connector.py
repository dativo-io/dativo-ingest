import datetime
from pathlib import Path

import pytest
import yaml

from dativo_ingest.config import JobConfig
from dativo_ingest.connectors.factory import ExtractorFactory


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


@pytest.mark.unit
def test_mimesis_extractor_generates_expected_rows(tmp_path: Path) -> None:
    asset_path = tmp_path / "asset.yaml"
    output_path = tmp_path / "synthetic.parquet"

    asset_definition = {
        "$schema": "schemas/odcs/dativo-odcs-3.0.2-extended.schema.json",
        "apiVersion": "v3.0.2",
        "kind": "DataContract",
        "name": "tmp_customers",
        "version": "1.0",
        "source_type": "mimesis",
        "object": "tmp_customers",
        "team": {"owner": "tests@dativo.ai"},
        "schema": [
            {"name": "customer_id", "type": "integer", "required": True},
            {"name": "name", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": True},
            {"name": "signup_date", "type": "date", "required": True},
            {"name": "account_balance", "type": "double", "required": False},
            {"name": "ingest_date", "type": "date", "required": True},
        ],
        "target": {
            "file_format": "parquet",
            "partitioning": ["ingest_date"],
            "target_path": str(output_path),
        },
    }

    _write_yaml(asset_path, asset_definition)

    job_path = tmp_path / "job.yaml"
    job_config_payload = {
        "tenant_id": "test_tenant",
        "source_connector": "mimesis",
        "source_connector_path": "connectors/examples/mimesis.yaml",
        "target_connector": "iceberg",
        "target_connector_path": "connectors/examples/iceberg.yaml",
        "asset": "tmp_customers",
        "asset_path": str(asset_path),
        "source": {
            "object": "tmp_customers",
            "engine": {
                "type": "native",
                "options": {
                    "native": {
                        "row_count": 25,
                        "batch_size": 10,
                        "locale": "en",
                        "null_probability": 0.05,
                    }
                },
            },
        },
        "target": {
            "connection": {
                "s3": {
                    "endpoint": "http://localhost:9000",
                    "bucket": "test-bucket",
                    "access_key_id": "test",
                    "secret_access_key": "test",
                    "region": "us-east-1",
                    "path_style_access": True,
                }
            }
        },
    }

    _write_yaml(job_path, job_config_payload)

    job_config = JobConfig.from_yaml(job_path)
    source_config = job_config.get_source()

    extractor, _ = ExtractorFactory.create(source_config, job_config)
    batches = list(extractor.extract())

    total_records = sum(len(batch) for batch in batches)
    assert total_records == 25
    assert all("ingest_date" in record for batch in batches for record in batch)

    sample_record = batches[0][0]
    assert {"customer_id", "name", "email", "signup_date", "account_balance"}.issubset(
        sample_record.keys()
    )
    assert (
        isinstance(sample_record["signup_date"], datetime.date)
        or sample_record["signup_date"] is None
    )

    assert output_path.exists(), "Synthetic Parquet output was not materialized"
