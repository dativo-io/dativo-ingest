"""Unit tests for pluggable secret managers."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from dativo_ingest.secrets import (
    AWSSecretsManager,
    EnvironmentSecretManager,
    FilesystemSecretManager,
    GCPSecretManager,
    HashicorpVaultSecretManager,
    load_secrets,
)


def test_environment_secret_manager_supports_formats(monkeypatch):
    monkeypatch.setenv(
        "DATIVO_SECRET__TENANT_A__postgres__env",
        "PGUSER=service\nPGPASSWORD=${PG_PASSWORD}",
    )
    monkeypatch.setenv("PG_PASSWORD", "p@ss")
    monkeypatch.setenv(
        "DATIVO_SECRET__GLOBAL__stripe_api_key__text",
        "sk_live_123",
    )
    manager = EnvironmentSecretManager()

    secrets = manager.load_secrets("tenant_a")

    assert secrets["postgres"]["PGUSER"] == "service"
    assert secrets["postgres"]["PGPASSWORD"] == "p@ss"
    assert secrets["stripe_api_key"] == "sk_live_123"


def test_filesystem_secret_manager_reads_json_and_env(tmp_path: Path):
    tenant_dir = tmp_path / "tenant_a"
    tenant_dir.mkdir()
    (tenant_dir / "gsheets.json").write_text(
        '{"client_email": "svc@acme.com"}', encoding="utf-8"
    )
    (tenant_dir / "postgres.env").write_text(
        "PGHOST=db\nPGUSER=svc\nPGPASSWORD=secret", encoding="utf-8"
    )

    manager = FilesystemSecretManager(secrets_dir=tmp_path)
    secrets = manager.load_secrets("tenant_a")

    assert secrets["gsheets"]["client_email"] == "svc@acme.com"
    assert secrets["postgres"]["PGHOST"] == "db"


def test_hashicorp_vault_secret_manager_merges_paths():
    mock_client = MagicMock()
    mock_client.secrets.kv.v2.read_secret_version.side_effect = [
        {"data": {"data": {"token": "abc"}}},
        {"data": {"data": {"nested": {"secret": "xyz"}}}},
    ]

    manager = HashicorpVaultSecretManager(
        address="http://vault.local",
        token="root",
        path_template="tenants/{tenant}",
        paths=["tenants/{tenant}", "shared/{tenant}"],
        client_factory=lambda: mock_client,
    )

    secrets = manager.load_secrets("tenant1")

    assert secrets["token"] == "abc"
    assert secrets["nested"]["secret"] == "xyz"


def test_aws_secrets_manager_supports_discrete_definitions():
    mock_client = MagicMock()
    mock_client.get_secret_value.return_value = {"SecretString": '{"url":"db"}'}
    manager = AWSSecretsManager(
        region_name="us-east-1",
        secrets=[{"name": "postgres", "format": "json"}],
        client=mock_client,
    )

    secrets = manager.load_secrets("tenant1")

    assert secrets["postgres"]["url"] == "db"
    mock_client.get_secret_value.assert_called_once()


def test_aws_secrets_manager_bundle(monkeypatch):
    mock_client = MagicMock()
    mock_client.get_secret_value.return_value = {
        "SecretString": '{"postgres": {"url": "db"}}'
    }
    manager = AWSSecretsManager(
        region_name="us-east-1",
        bundle_secret_id_template="bundle/{tenant}",
        client=mock_client,
    )

    secrets = manager.load_secrets("tenant1")

    assert secrets["postgres"]["url"] == "db"


def test_gcp_secret_manager_bundle():
    mock_client = MagicMock()
    mock_client.access_secret_version.return_value = SimpleNamespace(
        payload=SimpleNamespace(data=b'{"stripe_api_key":"sk_live"}')
    )
    manager = GCPSecretManager(
        project_id="dativo-test",
        bundle_secret_id_template="bundle-{tenant}",
        client=mock_client,
    )

    secrets = manager.load_secrets("tenant1")

    assert secrets["stripe_api_key"] == "sk_live"


def test_load_secrets_defaults_to_env(monkeypatch):
    monkeypatch.setenv("DATIVO_SECRET__TENANT_X__api_key__text", "abc123")

    secrets = load_secrets("tenant_x")

    assert secrets["api_key"] == "abc123"
