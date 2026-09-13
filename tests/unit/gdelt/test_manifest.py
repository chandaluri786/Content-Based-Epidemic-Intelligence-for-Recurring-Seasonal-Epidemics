import pytest

from pipeline.gdelt.manifest import IngestionManifest


@pytest.mark.unit
class TestIngestionManifest:
    def test_unknown_stamp_is_not_done(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        assert manifest.is_done("20230101000000") is False

    def test_ok_stamp_is_done(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        manifest.mark_done("20230101000000", status="ok", matched_count=3)
        assert manifest.is_done("20230101000000") is True

    def test_not_found_stamp_is_done_and_never_retried(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        manifest.mark_done("20140101000000", status="not_found")
        assert manifest.is_done("20140101000000") is True

    def test_parse_failed_stamp_is_done_and_not_retried(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        manifest.mark_done("20230101000000", status="parse_failed")
        assert manifest.is_done("20230101000000") is True

    def test_failed_transient_stamp_is_not_done_and_should_be_retried(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        manifest.mark_done("20230101000000", status="failed_transient")
        assert manifest.is_done("20230101000000") is False

    def test_state_persists_across_manifest_instances(self, tmp_path):
        path = str(tmp_path / "manifest.jsonl")
        manifest_a = IngestionManifest(path)
        manifest_a.mark_done("20230101000000", status="ok", matched_count=5)

        manifest_b = IngestionManifest(path)
        assert manifest_b.is_done("20230101000000") is True
        assert manifest_b.matched_count("20230101000000") == 5

    def test_a_later_mark_done_overwrites_the_earlier_status(self, tmp_path):
        path = str(tmp_path / "manifest.jsonl")
        manifest = IngestionManifest(path)
        manifest.mark_done("20230101000000", status="failed_transient")
        manifest.mark_done("20230101000000", status="ok", matched_count=2)

        reloaded = IngestionManifest(path)
        assert reloaded.is_done("20230101000000") is True
        assert reloaded.matched_count("20230101000000") == 2

    def test_matched_count_defaults_to_zero(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        manifest.mark_done("20230101000000", status="not_found")
        assert manifest.matched_count("20230101000000") == 0

    def test_matched_count_for_unknown_stamp_is_zero(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        assert manifest.matched_count("unknown") == 0

    def test_total_matched_sums_all_ok_entries(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        manifest.mark_done("a", status="ok", matched_count=3)
        manifest.mark_done("b", status="ok", matched_count=4)
        manifest.mark_done("c", status="not_found")
        assert manifest.total_matched() == 7
