import os


def test_prometheus_metrics_are_populated() -> None:
    # Ensure we are NOT in multiprocess mode for this unit test.
    os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)

    from prometheus_client import exposition

    from dativo_ingest.metrics import JobRunMetrics, build_job_labels

    m = JobRunMetrics(
        build_job_labels(
            tenant_id="t1",
            job_name="job1",
            connector_type="csv",
            mode="self_hosted",
        )
    )

    m.inc_records(10, phase="extracted")
    m.inc_records(8, phase="written")
    m.inc_records(2, phase="invalid")
    m.inc_bytes(1234, phase="written")
    m.inc_retries(1)
    m.observe_extract_seconds(0.5)
    m.observe_load_seconds(0.25)
    m.observe_runtime_seconds(1.0)

    payload = exposition.generate_latest()
    text = payload.decode("utf-8")

    assert "dativo_ingest_records_total" in text
    assert "dativo_ingest_bytes_total" in text
    assert "dativo_ingest_retries_total" in text
    assert "dativo_ingest_extract_seconds" in text
    assert "dativo_ingest_load_seconds" in text
    assert "dativo_ingest_runtime_seconds" in text

