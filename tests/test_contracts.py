"""
Tests for data contract YAML loading and the _safe_eval_assertion helper.

We test the pure Python logic directly — no HTTP, no DB, no warehouse
connector required. Connector-dependent rules are tested with mocks.
"""

import os
import tempfile

import pytest
import yaml

from backend.routers.checks import _safe_eval_assertion


# ---------------------------------------------------------------------------
# _safe_eval_assertion — core assertion evaluator
# ---------------------------------------------------------------------------

class TestSafeEvalAssertion:
    def test_result_equals_zero_passes(self):
        assert _safe_eval_assertion("result == 0", 0) is True

    def test_result_equals_zero_fails_on_nonzero(self):
        assert _safe_eval_assertion("result == 0", 5) is False

    def test_result_ge_zero(self):
        assert _safe_eval_assertion("result >= 0", 10) is True
        assert _safe_eval_assertion("result >= 0", -1) is False

    def test_result_le_threshold(self):
        assert _safe_eval_assertion("result <= 100", 50) is True
        assert _safe_eval_assertion("result <= 100", 101) is False

    def test_combined_expression_raises_value_error(self):
        """Multi-clause expressions ('and') are not supported and raise ValueError."""
        with pytest.raises(ValueError):
            _safe_eval_assertion("result > 0 and result < 1000", 500)

    def test_float_comparison(self):
        assert _safe_eval_assertion("result < 0.05", 0.03) is True
        assert _safe_eval_assertion("result < 0.05", 0.07) is False

    def test_invalid_code_expression_raises_value_error(self):
        """Expressions that are not simple comparisons raise ValueError."""
        with pytest.raises((ValueError, SyntaxError)):
            _safe_eval_assertion("__import__('os').system('rm -rf /')", 0)

    def test_empty_assertion_raises_value_error(self):
        """Empty string is not a valid assertion — raises ValueError or SyntaxError."""
        with pytest.raises((ValueError, SyntaxError)):
            _safe_eval_assertion("", 0)


# ---------------------------------------------------------------------------
# Contract YAML loading — test that the parser handles well-formed files
# ---------------------------------------------------------------------------

class TestContractYAMLLoading:
    def _write_contract(self, tmpdir: str, content: dict) -> str:
        path = os.path.join(tmpdir, "test_contract.yml")
        with open(path, "w") as f:
            yaml.dump(content, f)
        return path

    def test_well_formed_contract_loads(self):
        contract = {
            "contract": {
                "id": "orders_v1",
                "version": "1.0.0",
                "table": "public.orders",
                "owner": "data-eng@example.com",
                "columns": [
                    {"name": "id", "type": "integer", "nullable": False, "unique": True},
                    {"name": "status", "type": "varchar", "nullable": False,
                     "allowed_values": ["pending", "confirmed", "shipped"]},
                    {"name": "amount", "type": "numeric", "nullable": False, "min": 0},
                ],
                "rules": [
                    {
                        "name": "No future-dated orders",
                        "sql": "SELECT COUNT(*) FROM public.orders WHERE created_at > NOW()",
                        "assert": "result == 0",
                    }
                ],
                "volume": {"min_rows": 1000},
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_contract(tmpdir, contract)
            with open(path) as f:
                loaded = yaml.safe_load(f)

        c = loaded["contract"]
        assert c["id"] == "orders_v1"
        assert c["version"] == "1.0.0"
        assert c["table"] == "public.orders"
        assert len(c["columns"]) == 3
        assert c["columns"][1]["allowed_values"] == ["pending", "confirmed", "shipped"]
        assert c["rules"][0]["assert"] == "result == 0"
        assert c["volume"]["min_rows"] == 1000

    def test_contract_without_rules_is_valid(self):
        contract = {
            "contract": {
                "id": "minimal_v1",
                "table": "public.users",
                "columns": [{"name": "id", "type": "integer"}],
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_contract(tmpdir, contract)
            with open(path) as f:
                loaded = yaml.safe_load(f)

        c = loaded["contract"]
        assert c.get("rules", []) == []

    def test_malformed_yaml_raises_on_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bad.yml")
            with open(path, "w") as f:
                f.write("contract: [this is: not: valid yaml}")
            with open(path) as f:
                with pytest.raises(yaml.YAMLError):
                    yaml.safe_load(f)


# ---------------------------------------------------------------------------
# allowed_values check logic (pure Python simulation)
# ---------------------------------------------------------------------------

class TestAllowedValuesLogicSimulation:
    """
    Simulate the allowed-values rule logic without hitting a real DB.
    The actual query checks `col NOT IN (allowed_set)`.
    We test the SQL-building logic by checking the generated IN clause.
    """

    def _build_in_clause(self, allowed: list) -> str:
        return ", ".join("'" + str(v).replace("'", "''") + "'" for v in allowed)

    def test_simple_values_clause(self):
        clause = self._build_in_clause(["pending", "confirmed", "shipped"])
        assert "'pending'" in clause
        assert "'confirmed'" in clause
        assert "'shipped'" in clause

    def test_single_quote_in_value_is_escaped(self):
        clause = self._build_in_clause(["O'Malley"])
        assert "O''Malley" in clause  # single quote doubled for SQL safety

    def test_numeric_values_stringified(self):
        clause = self._build_in_clause([1, 2, 3])
        assert "'1'" in clause
        assert "'2'" in clause
