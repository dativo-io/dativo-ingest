"""Tests for cloud-backed plugin resolution."""

from types import SimpleNamespace

from dativo_ingest.cloud_plugins import CloudPluginResolver, is_cloud_uri


def test_resolve_local_path_passthrough(tmp_path):
    """Ensure local paths are returned as-is."""
    plugin_file = tmp_path / "plugin.py"
    plugin_file.write_text("print('local')")

    resolver = CloudPluginResolver(cache_dir=str(tmp_path / "cache"))
    resolved = resolver.resolve(str(plugin_file))

    assert resolved == plugin_file


def test_resolve_s3_uri_downloads_once(tmp_path, monkeypatch):
    """S3 URIs should download once and then serve from cache."""
    plugin_bytes = b"class Test: ..."
    downloads = []

    class FakeS3Client:
        def download_fileobj(self, bucket, key, file_obj):
            downloads.append((bucket, key))
            assert bucket == "my-bucket"
            assert key == "plugins/test_reader.py"
            file_obj.write(plugin_bytes)

    fake_boto3 = SimpleNamespace(client=lambda service: FakeS3Client())
    monkeypatch.setattr(
        "dativo_ingest.cloud_plugins.boto3", fake_boto3, raising=False
    )

    resolver = CloudPluginResolver(cache_dir=str(tmp_path / "cache"))
    uri = "s3://my-bucket/plugins/test_reader.py"

    path = resolver.resolve(uri)
    assert path.exists()
    assert path.read_bytes() == plugin_bytes

    # Second call should use cached file (no additional downloads)
    cached = resolver.resolve(uri)
    assert cached == path
    assert len(downloads) == 1


def test_resolve_gcs_uri_downloads_once(tmp_path, monkeypatch):
    """GCS URIs should download once and cache subsequent reads."""
    plugin_bytes = b"print('gcs')"
    downloads = []

    class FakeBlob:
        def download_to_file(self, file_obj):
            downloads.append("gcs")
            file_obj.write(plugin_bytes)

    class FakeBucket:
        def blob(self, key):
            assert key == "plugins/test_reader.py"
            return FakeBlob()

    class FakeClient:
        def bucket(self, bucket_name):
            assert bucket_name == "my-bucket"
            return FakeBucket()

    fake_storage = SimpleNamespace(
        Client=lambda *args, **kwargs: FakeClient()
    )
    monkeypatch.setattr(
        "dativo_ingest.cloud_plugins.storage", fake_storage, raising=False
    )

    resolver = CloudPluginResolver(cache_dir=str(tmp_path / "cache"))
    uri = "gs://my-bucket/plugins/test_reader.py"

    path = resolver.resolve(uri)
    assert path.exists()
    assert path.read_bytes() == plugin_bytes

    resolver.resolve(uri)
    assert len(downloads) == 1


def test_is_cloud_uri_helper():
    """Verify helper correctly identifies supported schemes."""
    assert is_cloud_uri("s3://bucket/plugin.py")
    assert is_cloud_uri("gs://bucket/libplugin.so")
    assert not is_cloud_uri("/app/plugins/local.py")
    assert not is_cloud_uri("file:///tmp/plugin.py")
