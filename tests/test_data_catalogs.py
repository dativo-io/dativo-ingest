import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import (
    AssetDefinition,
    TargetConfig,
    OpenMetadataCatalogConfig,
    AwsGlueCatalogConfig,
)
from dativo_ingest.data_catalogs import DataCatalogSyncManager


@pytest.fixture
def asset_definition():
    return AssetDefinition(
        name="customers",
        version="1.0",
        source_type="postgres",
        object="public.customers",
        domain="sales",
        dataProduct="customer360",
        schema=[
            {"name": "id", "type": "integer", "required": True},
            {"name": "email", "type": "string", "classification": "PII"},
        ],
        team={"owner": "data@example.com"},
    )


@pytest.fixture
def target_config():
    return TargetConfig(type="iceberg", partitioning=["ingest_date"])


class MockResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("http error")

    def json(self):
        return self._payload


class MockSession:
    def __init__(self):
        self.headers = {}
        self.calls = []
        self.last_payload = None

    def get(self, url, timeout=None, verify=None):
        self.calls.append(("GET", url))
        return MockResponse(
            payload={
                "id": "schema-id",
                "name": "public",
                "fullyQualifiedName": "svc.analytics.public",
            }
        )

    def put(self, url, data=None, timeout=None, verify=None):
        self.calls.append(("PUT", url))
        if data:
            self.last_payload = json.loads(data)
        return MockResponse(status_code=200)


class MockGlueClient:
    class exceptions:
        class EntityNotFoundException(Exception):
            pass

    def __init__(self):
        self.calls = {"create_table": [], "update_table": []}

    def get_table(self, **kwargs):
        raise self.exceptions.EntityNotFoundException()

    def create_table(self, **kwargs):
        self.calls["create_table"].append(kwargs)

    def update_table(self, **kwargs):
        self.calls["update_table"].append(kwargs)


def test_openmetadata_sync_builds_payload(asset_definition, target_config):
    session = MockSession()
    catalog_config = OpenMetadataCatalogConfig(
        server_url="https://metadata.example.com",
        service_name="svc",
        database="analytics",
        schema="public",
        auth_token="token",
        tags=["gold"],
    )

    manager = DataCatalogSyncManager(
        asset_definition=asset_definition,
        target_config=target_config,
        output_base_path="s3://lake/sales/customer360/customers",
        catalog_configs=[catalog_config],
        http_session_factory=lambda: session,
    )

    manager.sync()

    assert any(call[0] == "GET" for call in session.calls)
    assert any(call[0] == "PUT" for call in session.calls)
    assert session.last_payload is not None
    assert session.last_payload["name"] == "customers"
    assert session.last_payload["columns"][0]["name"] == "id"
    assert session.last_payload["columns"][1]["tags"] == [{"tagFQN": "PII"}]


def test_aws_glue_sync_creates_table(asset_definition, target_config):
    glue_client = MockGlueClient()
    catalog_config = AwsGlueCatalogConfig(
        database="analytics",
        region="us-east-1",
        storage_location="s3://lake/sales/customer360/customers",
    )

    manager = DataCatalogSyncManager(
        asset_definition=asset_definition,
        target_config=target_config,
        output_base_path="s3://lake/sales/customer360/customers",
        catalog_configs=[catalog_config],
        glue_client_factory=lambda _: glue_client,
    )

    manager.sync()

    assert len(glue_client.calls["create_table"]) == 1
    table_input = glue_client.calls["create_table"][0]["TableInput"]
    assert table_input["Name"] == "customers"
    assert table_input["PartitionKeys"][0]["Name"] == "ingest_date"
    assert table_input["StorageDescriptor"]["Columns"][0]["Name"] == "id"
