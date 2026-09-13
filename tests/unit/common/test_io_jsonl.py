import json

import pytest

from pipeline.common.io_jsonl import append_jsonl, read_jsonl_tolerant


@pytest.mark.unit
class TestAppendJsonl:
    def test_appends_a_line_to_a_new_file(self, tmp_path):
        path = tmp_path / "out.jsonl"
        append_jsonl(str(path), {"a": 1})
        assert path.read_text() == json.dumps({"a": 1}) + "\n"

    def test_appends_multiple_lines_in_order(self, tmp_path):
        path = tmp_path / "out.jsonl"
        append_jsonl(str(path), {"a": 1})
        append_jsonl(str(path), {"a": 2})
        lines = path.read_text().splitlines()
        assert [json.loads(l) for l in lines] == [{"a": 1}, {"a": 2}]


@pytest.mark.unit
class TestReadJsonlTolerant:
    def test_reads_all_valid_lines(self, tmp_path):
        path = tmp_path / "in.jsonl"
        path.write_text('{"a": 1}\n{"a": 2}\n')
        assert read_jsonl_tolerant(str(path)) == [{"a": 1}, {"a": 2}]

    def test_missing_file_returns_empty_list(self, tmp_path):
        path = tmp_path / "missing.jsonl"
        assert read_jsonl_tolerant(str(path)) == []

    def test_drops_truncated_last_line(self, tmp_path):
        path = tmp_path / "in.jsonl"
        path.write_text('{"a": 1}\n{"a": 2}\n{"a": 3, "trunca')
        assert read_jsonl_tolerant(str(path)) == [{"a": 1}, {"a": 2}]

    def test_skips_blank_lines(self, tmp_path):
        path = tmp_path / "in.jsonl"
        path.write_text('{"a": 1}\n\n{"a": 2}\n')
        assert read_jsonl_tolerant(str(path)) == [{"a": 1}, {"a": 2}]

    def test_malformed_line_before_the_last_line_raises(self, tmp_path):
        path = tmp_path / "in.jsonl"
        path.write_text('{"a": 1}\nnot json at all\n{"a": 2}\n')
        with pytest.raises(json.JSONDecodeError):
            read_jsonl_tolerant(str(path))
