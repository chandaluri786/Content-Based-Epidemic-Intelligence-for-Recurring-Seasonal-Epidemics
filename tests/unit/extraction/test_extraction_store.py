import pytest

from pipeline.extraction.extraction_store import ExtractionStore


@pytest.mark.unit
class TestExtractionStore:
    def test_unknown_url_is_not_done(self, tmp_path):
        store = ExtractionStore(str(tmp_path / "store.jsonl"))
        assert store.is_done("http://example.com/a") is False

    def test_recorded_url_is_done(self, tmp_path):
        store = ExtractionStore(str(tmp_path / "store.jsonl"))
        store.record(
            "http://example.com/a",
            stamp="20230101000000",
            status="extracted",
            extraction={"confidence": 0.9},
        )
        assert store.is_done("http://example.com/a") is True

    def test_state_persists_across_instances(self, tmp_path):
        path = str(tmp_path / "store.jsonl")
        store_a = ExtractionStore(path)
        store_a.record("http://example.com/a", stamp="20230101000000", status="skipped_prefilter")

        store_b = ExtractionStore(path)
        assert store_b.is_done("http://example.com/a") is True

    def test_record_persists_all_fields(self, tmp_path):
        path = str(tmp_path / "store.jsonl")
        store = ExtractionStore(path)
        store.record(
            "http://example.com/a",
            stamp="20230101000000",
            status="extracted",
            extraction={"confidence": 0.9, "relevant": True},
            model="openai/gpt-oss-120b",
        )

        reloaded_records = list(ExtractionStore(path).iter_records())
        assert reloaded_records == [
            {
                "url": "http://example.com/a",
                "stamp": "20230101000000",
                "status": "extracted",
                "extraction": {"confidence": 0.9, "relevant": True},
                "reason": None,
                "model": "openai/gpt-oss-120b",
            }
        ]

    def test_model_defaults_to_none_when_not_provided(self, tmp_path):
        store = ExtractionStore(str(tmp_path / "store.jsonl"))
        store.record("http://example.com/a", stamp="20230101000000", status="not_retrievable")
        assert next(iter(store.iter_records()))["model"] is None

    def test_record_with_failure_reason(self, tmp_path):
        store = ExtractionStore(str(tmp_path / "store.jsonl"))
        store.record("http://example.com/a", stamp="20230101000000", status="failed", reason="boom")
        records = list(store.iter_records())
        assert records[0]["reason"] == "boom"
        assert records[0]["extraction"] is None
