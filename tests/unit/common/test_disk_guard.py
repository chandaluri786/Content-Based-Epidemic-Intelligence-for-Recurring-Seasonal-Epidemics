from unittest.mock import patch

import pytest

from pipeline.common.disk_guard import DiskSpaceError, ensure_min_free_space, free_gb


@pytest.mark.unit
class TestFreeGb:
    def test_returns_positive_float_for_real_path(self, tmp_path):
        assert free_gb(str(tmp_path)) > 0


@pytest.mark.unit
class TestEnsureMinFreeSpace:
    def test_passes_silently_when_space_is_sufficient(self, tmp_path):
        with patch("pipeline.common.disk_guard.free_gb", return_value=50.0):
            ensure_min_free_space(min_gb=5.0, path=str(tmp_path))

    def test_raises_when_space_is_below_threshold(self, tmp_path):
        with (
            patch("pipeline.common.disk_guard.free_gb", return_value=2.0),
            pytest.raises(DiskSpaceError),
        ):
            ensure_min_free_space(min_gb=5.0, path=str(tmp_path))

    def test_raises_at_exact_boundary_minus_epsilon(self, tmp_path):
        with (
            patch("pipeline.common.disk_guard.free_gb", return_value=4.999),
            pytest.raises(DiskSpaceError),
        ):
            ensure_min_free_space(min_gb=5.0, path=str(tmp_path))

    def test_passes_at_exact_boundary(self, tmp_path):
        with patch("pipeline.common.disk_guard.free_gb", return_value=5.0):
            ensure_min_free_space(min_gb=5.0, path=str(tmp_path))
