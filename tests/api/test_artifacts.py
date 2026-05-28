from tradingagents.api.artifacts import LocalArtifactStore


def test_local_artifact_store_writes_under_run_id(tmp_path):
    store = LocalArtifactStore(tmp_path)

    artifact = store.write_text(
        run_id="run_abc",
        kind="report_md",
        relative_path="reports/complete_report.md",
        content="hello",
        content_type="text/markdown",
    )

    assert artifact.storage_key == "run_abc/reports/complete_report.md"
    assert (tmp_path / artifact.storage_key).read_text() == "hello"
    assert artifact.size_bytes == 5
    assert artifact.sha256
