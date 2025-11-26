"""Tests for data catalog lineage publishing."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

from dativo_ingest.config import (
    AssetDefinition,
    CatalogTargetConfig,
    JobConfig,
    SourceConfig,
    TargetConfig,
    TeamModel,
)
from dativo_ingest.data_catalogs import (
    AwsGlueCatalogPublisher,
    DatabricksUnityCatalogPublisher,
    NessieCatalogPublisher,
    OpenMetadataCatalogPublisher,
    build_lineage_payload,
)


@pytest.fixture
def sample_asset():
    return AssetDefinition(
        name="test_employee",
        version="1.0",
        domain="analytics",
        source_type="csv",
        object="employees",
        schema=[
            {"name": "employee_id", "type": "integer", "required": True},
            {"name": "email", "type": "string", "required": True, "classification": "PII"},
        ],
        team=TeamModel(owner="data-team@example.com"),
    )


@pytest.fixture
def sample_job_config():
    return JobConfig(
        tenant_id="tenant_a",
        source_connector_path="connectors/csv.yaml",
        target_connector_path="connectors/iceberg.yaml",
        asset_path="assets/csv/v1.0/test_employee.yaml",
    )


@pytest.fixture
def sample_source_config():
    return SourceConfig(type="csv", files=[{"path": "s3://landing/employees.csv"}])


@pytest.fixture
def sample_target_config():
    return TargetConfig(
        type="iceberg",
        catalog="nessie",
        branch="main",
        warehouse="s3://warehouse",
        connection={"s3": {"bucket": "analytics-lake"}},
    )


@pytest.fixture
def sample_file_metadata():
    return [
        {
            "path": "s3://analytics-lake/analytics/hr/test_employee/file.parquet",
            "size_bytes": 1024,
            "record_count": 2,
        }
    ]


@pytest.fixture
def sample_totals():
    return {
        "total_records": 2,
        "valid_records": 2,
        "files_written": 1,
        "has_errors": False,
        "validation_mode": "strict",
    }


@pytest.fixture
def lineage_payload(
    sample_job_config,
    sample_asset,
    sample_source_config,
    sample_target_config,
    sample_file_metadata,
    sample_totals,
):
    return build_lineage_payload(
        job_config=sample_job_config,
        asset_definition=sample_asset,
        source_config=sample_source_config,
        target_config=sample_target_config,
        file_metadata=sample_file_metadata,
        commit_result={
            "commit_id": "abc123",
            "branch": "main",
            "table_name": "analytics.test_employee",
            "files_added": 1,
        },
        totals=sample_totals,
        source_tags={"email": "pii"},
    )


def test_build_lineage_payload_contains_owners_and_tags(lineage_payload):
    assert "classification.fields.email" in lineage_payload.tags
    assert lineage_payload.owners == ["data-team@example.com"]
    assert lineage_payload.files[0]["path"].startswith("s3://")
    assert lineage_payload.commit["table_name"] == "analytics.test_employee"


def test_aws_glue_publisher_updates_parameters(lineage_payload):
    target = CatalogTargetConfig(
        type="aws_glue",
        database="analytics",
        table="test_employee",
        region="us-east-1",
    )
    publisher = AwsGlueCatalogPublisher(target)

    with patch("dativo_ingest.data_catalogs.boto3") as mock_boto:
        client = mock_boto.client.return_value
        client.get_table.return_value = {
            "Table": {
                "Name": "test_employee",
                "StorageDescriptor": {"Columns": [], "Location": "s3://warehouse"},
                "Parameters": {},
            }
        }
        client.update_table.return_value = {}

        result = publisher.publish(lineage_payload)

        assert result["database"] == "analytics"
        assert client.update_table.call_count == 1
        parameters = client.update_table.call_args.kwargs["TableInput"]["Parameters"]
        assert any(
            key.startswith("dativo.metadata.asset.name") for key in parameters.keys()
        )


def test_databricks_publisher_calls_rest_endpoint(lineage_payload):
    target = CatalogTargetConfig(
        type="databricks_unity",
        workspace_url="https://example.cloud.databricks.com",
        token="abc",
        catalog="main",
        schema="analytics",
        table="test_employee",
    )
    publisher = DatabricksUnityCatalogPublisher(target)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None

    with patch("dativo_ingest.data_catalogs.requests.post", return_value=mock_response) as mock_post:
        result = publisher.publish(lineage_payload)

    assert result["status_code"] == 200
    assert mock_post.call_count == 1
    posted_body = mock_post.call_args.kwargs["json"]
    assert posted_body["downstream"]["name"].endswith("test_employee")
    assert posted_body["details"]["dativoMetadata"]["asset"]["name"] == "test_employee"


def test_nessie_publisher_reuses_iceberg_committer(lineage_payload):
    target = CatalogTargetConfig(
        type="nessie",
        catalog="nessie",
        branch="main",
    )
    publisher = NessieCatalogPublisher(target)

    with patch("dativo_ingest.data_catalogs.IcebergCommitter") as mock_committer_cls:
        committer = mock_committer_cls.return_value
        committer._create_catalog.return_value = MagicMock()
        committer._update_table_properties.return_value = None

        result = publisher.publish(lineage_payload)

    assert result["table"] == "analytics.test_employee"
    committer._update_table_properties.assert_called_once()


class _RecordingHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # pragma: no cover - exercised in integration style test
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        self.server.received.append({"path": self.path, "body": body})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format, *args):  # pragma: no cover - silence logging
        return


def test_openmetadata_publisher_smoke(lineage_payload):
    server = HTTPServer(("localhost", 0), _RecordingHandler)
    server.received: List[Dict[str, bytes]] = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    port = server.server_address[1]
    target = CatalogTargetConfig(
        type="openmetadata",
        service="demo_service",
        database="analytics",
        schema="hr",
        table="test_employee",
        uri=f"http://localhost:{port}/api",
    )
    publisher = OpenMetadataCatalogPublisher(target)

    try:
        result = publisher.publish(lineage_payload)
        assert result["status_code"] == 200
        assert any(
            rec["path"] == "/api/v1/lineage/addLineage" for rec in server.received
        )
        body = json.loads(server.received[0]["body"])
        assert body["edge"]["toEntity"]["fullyQualifiedName"].endswith("test_employee")
    finally:
        server.shutdown()
        thread.join()
