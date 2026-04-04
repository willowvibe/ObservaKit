"""
ObservaKit — Data Contracts Router
Validates tables against producer-defined data contracts (schema + business rules).

What is a Data Contract?
  A formal, versioned agreement between a data producer (e.g. an upstream team or
  service) and a data consumer (e.g. an analytics team or ML pipeline) about:
    - Which columns must exist and their types
    - Which columns must never be null
    - Allowed value sets for categorical columns
    - Row count / freshness SLAs
    - Custom SQL business rules

Why it matters for portfolio / clients:
  - Data contracts are one of the hottest topics in modern data engineering (2024-2026).
  - Frameworks like dbt Contracts, Soda Agreements, and PayPal's open-source spec are
    gaining traction. ObservaKit's lightweight YAML-based contracts give small teams a
    head start without paying for enterprise tools.
  - In practice: catches breaking changes before consumers are impacted, creates
    accountability between teams, and satisfies data governance requirements.

Contract file format (YAML in config/contracts/*.yml):
  contract:
    id: orders_v1
    version: "1.0.0"
    table: public.orders
    owner: "data-eng@company.com"
    description: "Core orders table — produced by the ingestion pipeline"
    columns:
      - name: id
        type: integer
        nullable: false
        unique: true
      - name: status
        type: varchar
        nullable: false
        allowed_values: [pending, confirmed, shipped, delivered, cancelled]
      - name: amount
        type: numeric
        nullable: false
        min: 0
    rules:
      - name: "No future-dated orders"
        sql: "SELECT COUNT(*) FROM public.orders WHERE created_at > NOW()"
        assert: "result == 0"
      - name: "Revenue non-negative"
        sql: "SELECT MIN(amount) FROM public.orders"
        assert: "result >= 0"
    freshness:
      warn_after: 2h
      fail_after: 6h
    volume:
      min_rows: 1000
"""

import glob
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from alerts.base import dispatch_alert
from backend.models import ContractValidationResult, get_db
from config.loader import load_config

logger = logging.getLogger(__name__)

router = APIRouter()

CONTRACTS_DIR = os.getenv("CONTRACTS_DIR", "config/contracts/")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.post("/validate")
def validate_contracts(
    contract_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Validate all contracts (or a single one by ID) against the live warehouse.
    Returns a detailed pass/fail report per contract rule.
    """
    contract_files = glob.glob(os.path.join(CONTRACTS_DIR, "*.yml"))
    if not contract_files:
        return {"message": f"No contract files found in {CONTRACTS_DIR}"}

    from connectors.base import get_warehouse_connector
    connector = get_warehouse_connector()

    all_results = []
    for cfile in contract_files:
        try:
            with open(cfile) as f:
                doc = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to parse contract file {cfile}: {e}")
            continue

        contract = doc.get("contract", {})
        cid = contract.get("id", os.path.basename(cfile))

        if contract_id and cid != contract_id:
            continue

        table = contract.get("table")
        if not table:
            logger.warning(f"Contract {cid} has no table — skipping")
            continue

        violations = []

        # --- Column presence and type checks ---
        try:
            live_schema = {col["name"]: col for col in connector.get_schema(table)}
        except Exception as e:
            logger.error(f"Could not fetch schema for {table}: {e}")
            violations.append({
                "rule": "schema_fetch",
                "passed": False,
                "detail": f"Could not connect to table: {e}",
            })
            live_schema = {}

        for col_spec in contract.get("columns", []):
            col_name = col_spec["name"]
            expected_type = col_spec.get("type", "").lower()
            nullable = col_spec.get("nullable", True)
            unique = col_spec.get("unique", False)
            allowed_values = col_spec.get("allowed_values")
            min_val = col_spec.get("min")
            max_val = col_spec.get("max")

            # Column existence
            if col_name not in live_schema:
                violations.append({
                    "rule": f"column_exists:{col_name}",
                    "passed": False,
                    "detail": f"Column '{col_name}' is missing from {table}",
                })
                continue

            live_col = live_schema[col_name]

            # Type check (case-insensitive prefix match — e.g. "integer" matches "integer4")
            if expected_type and not live_col.get("type", "").lower().startswith(expected_type.replace(" ", "_")):
                violations.append({
                    "rule": f"column_type:{col_name}",
                    "passed": False,
                    "detail": (
                        f"Column '{col_name}' expected type '{expected_type}', "
                        f"got '{live_col.get('type')}'"
                    ),
                })

            # Nullable constraint
            if not nullable:
                try:
                    null_result = connector.execute_query(
                        f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col_name} IS NULL"
                    )
                    null_count = int(null_result[0]["cnt"]) if null_result else 0
                    violations.append({
                        "rule": f"not_null:{col_name}",
                        "passed": null_count == 0,
                        "detail": f"{null_count} null values found in '{col_name}' (must be 0)",
                    })
                except Exception as e:
                    violations.append({"rule": f"not_null:{col_name}", "passed": False, "detail": str(e)})

            # Uniqueness constraint
            if unique:
                try:
                    dup_result = connector.execute_query(
                        f"""
                        SELECT COUNT(*) AS cnt FROM (
                            SELECT {col_name} FROM {table}
                            GROUP BY {col_name} HAVING COUNT(*) > 1
                        ) dups
                        """
                    )
                    dup_count = int(dup_result[0]["cnt"]) if dup_result else 0
                    violations.append({
                        "rule": f"unique:{col_name}",
                        "passed": dup_count == 0,
                        "detail": f"{dup_count} duplicate values found in '{col_name}'",
                    })
                except Exception as e:
                    violations.append({"rule": f"unique:{col_name}", "passed": False, "detail": str(e)})

            # Allowed values check
            if allowed_values:
                try:
                    # Build a safe IN clause using parameterised-style quoting
                    quoted = ", ".join(f"'{v}'" for v in allowed_values)
                    invalid_result = connector.execute_query(
                        f"""
                        SELECT COUNT(*) AS cnt FROM {table}
                        WHERE {col_name} IS NOT NULL
                          AND {col_name} NOT IN ({quoted})
                        """
                    )
                    invalid_count = int(invalid_result[0]["cnt"]) if invalid_result else 0
                    violations.append({
                        "rule": f"allowed_values:{col_name}",
                        "passed": invalid_count == 0,
                        "detail": (
                            f"{invalid_count} rows have values outside allowed set "
                            f"{allowed_values} in '{col_name}'"
                        ),
                    })
                except Exception as e:
                    violations.append({"rule": f"allowed_values:{col_name}", "passed": False, "detail": str(e)})

            # Min / max range
            if min_val is not None:
                try:
                    below_result = connector.execute_query(
                        f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col_name} < {min_val}"
                    )
                    below_count = int(below_result[0]["cnt"]) if below_result else 0
                    violations.append({
                        "rule": f"min_value:{col_name}",
                        "passed": below_count == 0,
                        "detail": f"{below_count} rows have {col_name} < {min_val}",
                    })
                except Exception as e:
                    violations.append({"rule": f"min_value:{col_name}", "passed": False, "detail": str(e)})

            if max_val is not None:
                try:
                    above_result = connector.execute_query(
                        f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col_name} > {max_val}"
                    )
                    above_count = int(above_result[0]["cnt"]) if above_result else 0
                    violations.append({
                        "rule": f"max_value:{col_name}",
                        "passed": above_count == 0,
                        "detail": f"{above_count} rows have {col_name} > {max_val}",
                    })
                except Exception as e:
                    violations.append({"rule": f"max_value:{col_name}", "passed": False, "detail": str(e)})

        # --- Volume check ---
        volume_spec = contract.get("volume", {})
        if volume_spec.get("min_rows") is not None:
            try:
                count_result = connector.execute_query(f"SELECT COUNT(*) AS cnt FROM {table}")
                row_count = int(count_result[0]["cnt"]) if count_result else 0
                min_rows = int(volume_spec["min_rows"])
                violations.append({
                    "rule": "min_rows",
                    "passed": row_count >= min_rows,
                    "detail": f"Row count {row_count:,} (required ≥ {min_rows:,})",
                })
            except Exception as e:
                violations.append({"rule": "min_rows", "passed": False, "detail": str(e)})

        # --- Custom SQL rules ---
        for rule_spec in contract.get("rules", []):
            rule_name = rule_spec.get("name", "custom_rule")
            sql = rule_spec.get("sql", "")
            assertion = rule_spec.get("assert", "result == 0")
            try:
                rule_result = connector.execute_query(sql)
                result_value = 0
                if rule_result and rule_result[0]:
                    result_value = list(rule_result[0].values())[0] or 0

                try:
                    passed = bool(eval(assertion, {"__builtins__": None}, {"result": result_value}))
                except Exception:
                    passed = False

                violations.append({
                    "rule": rule_name,
                    "passed": passed,
                    "detail": f"SQL returned {result_value}; assertion '{assertion}' → {passed}",
                })
            except Exception as e:
                violations.append({"rule": rule_name, "passed": False, "detail": str(e)})

        # --- Persist result summary ---
        total = len(violations)
        passed_count = sum(1 for v in violations if v["passed"])
        contract_passed = passed_count == total

        record = ContractValidationResult(
            contract_id=cid,
            contract_version=contract.get("version", "unknown"),
            table_name=table,
            passed=contract_passed,
            total_rules=total,
            passed_rules=passed_count,
            violations_json=violations,
            validated_at=datetime.now(timezone.utc),
        )
        db.add(record)

        if not contract_passed:
            failed_rules = [v["rule"] for v in violations if not v["passed"]]
            dispatch_alert(
                alert_type="contract",
                table_name=table,
                subject=f"📋 Contract Violation: {cid}",
                message=(
                    f"Contract `{cid}` (v{contract.get('version', '?')}) on `{table}` "
                    f"has {total - passed_count} violation(s).\n"
                    f"Failed rules: {', '.join(failed_rules)}"
                ),
            )

        all_results.append({
            "contract_id": cid,
            "version": contract.get("version"),
            "table": table,
            "passed": contract_passed,
            "total_rules": total,
            "passed_rules": passed_count,
            "violations": [v for v in violations if not v["passed"]],
        })

    db.commit()
    return {"contracts_validated": len(all_results), "results": all_results}


@router.get("/results")
def get_contract_results(
    contract_id: Optional[str] = None,
    table_name: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Return recent contract validation results."""
    query = (
        db.query(ContractValidationResult)
        .order_by(ContractValidationResult.validated_at.desc())
    )
    if contract_id:
        query = query.filter(ContractValidationResult.contract_id == contract_id)
    if table_name:
        query = query.filter(ContractValidationResult.table_name == table_name)

    records = query.limit(limit).all()
    return [
        {
            "id": r.id,
            "contract_id": r.contract_id,
            "version": r.contract_version,
            "table": r.table_name,
            "passed": r.passed,
            "total_rules": r.total_rules,
            "passed_rules": r.passed_rules,
            "violations": r.violations_json,
            "validated_at": r.validated_at.isoformat(),
        }
        for r in records
    ]
