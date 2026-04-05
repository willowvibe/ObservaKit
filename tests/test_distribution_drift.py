"""
Tests for distribution drift detection logic (_detect_drift) and the
snapshot comparison machinery.

We test the pure Python functions in backend/routers/distribution.py
directly — no HTTP, no DB, no warehouse connector required.
"""

import pytest

from backend.routers.distribution import _detect_drift


# ---------------------------------------------------------------------------
# Null-% drift detection
# ---------------------------------------------------------------------------

class TestNullPctDrift:
    def test_null_pct_below_threshold_no_drift(self):
        prev = {"null_pct": 0.02, "top_values": []}
        curr = {"null_pct": 0.03, "top_values": []}
        result = _detect_drift(prev, curr, "categorical", threshold=0.10, null_threshold=0.05)
        assert result["drifted"] is False

    def test_null_pct_above_threshold_triggers_drift(self):
        prev = {"null_pct": 0.01, "top_values": []}
        curr = {"null_pct": 0.10, "top_values": []}  # +9%, above 5% threshold
        result = _detect_drift(prev, curr, "categorical", threshold=0.10, null_threshold=0.05)
        assert result["drifted"] is True
        assert result["drift_type"] == "null_pct_change"

    def test_null_pct_exact_threshold_triggers_drift(self):
        prev = {"null_pct": 0.0, "top_values": []}
        curr = {"null_pct": 0.05, "top_values": []}  # exactly at threshold
        result = _detect_drift(prev, curr, "categorical", threshold=0.10, null_threshold=0.05)
        assert result["drifted"] is True

    def test_null_pct_decrease_also_detected(self):
        """A sudden drop in nulls (data cleaning) should also be flagged."""
        prev = {"null_pct": 0.20, "top_values": []}
        curr = {"null_pct": 0.01, "top_values": []}
        result = _detect_drift(prev, curr, "categorical", threshold=0.10, null_threshold=0.05)
        assert result["drifted"] is True
        assert result["drift_type"] == "null_pct_change"
        assert result["magnitude"] == pytest.approx(0.19, abs=1e-9)


# ---------------------------------------------------------------------------
# Categorical value-share shift
# ---------------------------------------------------------------------------

class TestCategoricalDrift:
    def _make_cat(self, values: dict, null_pct=0.0) -> dict:
        """Helper: build a categorical snapshot dict."""
        top_values = [{"value": k, "count": int(v * 1000), "pct": v} for k, v in values.items()]
        return {"null_pct": null_pct, "top_values": top_values}

    def test_stable_distribution_no_drift(self):
        prev = self._make_cat({"active": 0.80, "inactive": 0.19})
        curr = self._make_cat({"active": 0.81, "inactive": 0.18})  # 1% shift
        result = _detect_drift(prev, curr, "categorical", threshold=0.10, null_threshold=0.05)
        assert result["drifted"] is False

    def test_large_value_shift_triggers_drift(self):
        prev = self._make_cat({"active": 0.95, "cancelled": 0.05})
        curr = self._make_cat({"active": 0.50, "cancelled": 0.50})  # 45% shift on cancelled
        result = _detect_drift(prev, curr, "categorical", threshold=0.10, null_threshold=0.05)
        assert result["drifted"] is True
        assert result["drift_type"] == "value_share_shift"
        assert result["magnitude"] >= 0.40

    def test_new_value_appearing_triggers_drift(self):
        """A value that did not exist before now appearing at 20% is a drift."""
        prev = self._make_cat({"active": 0.95, "inactive": 0.05})
        curr = self._make_cat({"active": 0.75, "inactive": 0.05, "suspended": 0.20})
        result = _detect_drift(prev, curr, "categorical", threshold=0.10, null_threshold=0.05)
        assert result["drifted"] is True

    def test_value_disappearing_triggers_drift(self):
        prev = self._make_cat({"active": 0.80, "trial": 0.20})
        curr = self._make_cat({"active": 1.00})  # trial gone
        result = _detect_drift(prev, curr, "categorical", threshold=0.10, null_threshold=0.05)
        assert result["drifted"] is True


# ---------------------------------------------------------------------------
# Numeric mean-shift detection
# ---------------------------------------------------------------------------

class TestNumericDrift:
    def _make_num(self, mean, max_val=1000.0, null_pct=0.0) -> dict:
        return {
            "null_pct": null_pct,
            "mean": mean,
            "max": max_val,
            "min": 0.0,
            "percentiles": {},
            "histogram": [],
            "total_rows": 10000,
            "null_count": 0,
        }

    def test_stable_mean_no_drift(self):
        prev = self._make_num(mean=250.0, max_val=1000.0)
        curr = self._make_num(mean=255.0, max_val=1000.0)  # 0.5% shift
        result = _detect_drift(prev, curr, "numeric", threshold=0.10, null_threshold=0.05)
        assert result["drifted"] is False

    def test_large_mean_shift_triggers_drift(self):
        prev = self._make_num(mean=100.0, max_val=500.0)
        curr = self._make_num(mean=400.0, max_val=500.0)  # 60% of max shift
        result = _detect_drift(prev, curr, "numeric", threshold=0.10, null_threshold=0.05)
        assert result["drifted"] is True
        assert result["drift_type"] == "mean_shift"

    def test_no_drift_returns_clean_dict(self):
        prev = self._make_num(mean=100.0, max_val=200.0)
        curr = self._make_num(mean=102.0, max_val=200.0)
        result = _detect_drift(prev, curr, "numeric", threshold=0.10, null_threshold=0.05)
        assert result["drifted"] is False
        assert result["drift_type"] is None
        assert result["magnitude"] == 0

    def test_null_checked_before_mean(self):
        """Null drift (category-agnostic) should be detected first for numeric columns too."""
        prev = self._make_num(mean=100.0, max_val=200.0, null_pct=0.0)
        curr = self._make_num(mean=100.0, max_val=200.0, null_pct=0.10)
        result = _detect_drift(prev, curr, "numeric", threshold=0.10, null_threshold=0.05)
        assert result["drifted"] is True
        assert result["drift_type"] == "null_pct_change"
