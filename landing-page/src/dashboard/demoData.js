/**
 * ObservaKit — Frontend Demo Data
 * Returned by mockApiFetch() when the backend is unreachable so GitHub Pages
 * visitors can explore every dashboard tab with realistic sample data.
 */

const now = new Date();
const ago = (h = 0, m = 0) => new Date(now - h * 3600_000 - m * 60_000).toISOString();

// ---------------------------------------------------------------------------
// GET /status
// ---------------------------------------------------------------------------
export const DEMO_STATUS = {
  generated_at: ago(0, 2),
  window_hours: 24,
  summary: { healthy: 3, warn: 1, fail: 1 },
  tables: [
    { name: "analytics.daily_revenue", freshness: "warn",  volume: "ok",  quality: "ok",  schema: "ok",  last_checked: ago(0, 15), quality_pass_rate: 100 },
    { name: "analytics.user_events",   freshness: "ok",    volume: "ok",  quality: "ok",  schema: "ok",  last_checked: ago(0, 12), quality_pass_rate: 100 },
    { name: "public.customers",        freshness: "ok",    volume: "ok",  quality: "ok",  schema: "warn", last_checked: ago(0, 10), quality_pass_rate: 100 },
    { name: "public.orders",           freshness: "fail",  volume: "fail", quality: "fail", schema: "ok", last_checked: ago(0, 2),  quality_pass_rate: 60  },
    { name: "public.products",         freshness: "warn",  volume: "ok",  quality: "warn", schema: "ok", last_checked: ago(0, 8),  quality_pass_rate: 88  },
  ],
  pillars: {
    freshness: { last_checked: ago(0, 2)  },
    volume:    { last_checked: ago(0, 5)  },
    quality:   { last_checked: ago(0, 2)  },
    schema:    { last_detected: ago(6)    },
  },
  suppressions: { active: 1 },
};

// ---------------------------------------------------------------------------
// GET /freshness/?limit=100
// ---------------------------------------------------------------------------
export const DEMO_FRESHNESS = [
  { table: "public.orders",           lag_seconds: 17280, status: "fail", checked_at: ago(0, 2)  },
  { table: "analytics.daily_revenue", lag_seconds:  4320, status: "warn", checked_at: ago(0, 15) },
  { table: "public.products",         lag_seconds:  3900, status: "warn", checked_at: ago(0, 8)  },
  { table: "public.customers",        lag_seconds:   240, status: "ok",   checked_at: ago(0, 10) },
  { table: "analytics.user_events",   lag_seconds:   180, status: "ok",   checked_at: ago(0, 12) },
];

// ---------------------------------------------------------------------------
// GET /checks/results?limit=50
// ---------------------------------------------------------------------------
export const DEMO_CHECKS = [
  // public.orders — failures
  { check_name: "order_id must not be null",        table_name: "public.orders",           check_type: "soda",              passed: false, details: "3 null values found in last run",      executed_at: ago(0, 3)  },
  { check_name: "order_id must be unique",          table_name: "public.orders",           check_type: "soda",              passed: false, details: "2 duplicate order_ids detected",        executed_at: ago(0, 3)  },
  { check_name: "Orders table must not be empty",   table_name: "public.orders",           check_type: "soda",              passed: true,  details: null,                                    executed_at: ago(0, 3)  },
  { check_name: "amount must be non-negative",      table_name: "public.orders",           check_type: "great_expectations", passed: true,  details: null,                                    executed_at: ago(0, 3)  },
  { check_name: "status must be in allowed values", table_name: "public.orders",           check_type: "custom_sql",        passed: true,  details: null,                                    executed_at: ago(0, 3)  },
  // public.customers — clean
  { check_name: "customer_id must not be null",     table_name: "public.customers",        check_type: "soda",              passed: true,  details: null,                                    executed_at: ago(0, 10) },
  { check_name: "email must not be null",           table_name: "public.customers",        check_type: "soda",              passed: true,  details: null,                                    executed_at: ago(0, 10) },
  { check_name: "country must be 2-char ISO code",  table_name: "public.customers",        check_type: "great_expectations", passed: true,  details: null,                                    executed_at: ago(0, 10) },
  // public.products — one warning
  { check_name: "product_id must not be null",      table_name: "public.products",         check_type: "soda",              passed: true,  details: null,                                    executed_at: ago(0, 8)  },
  { check_name: "price must be positive",           table_name: "public.products",         check_type: "soda",              passed: true,  details: null,                                    executed_at: ago(0, 8)  },
  { check_name: "category must not be null",        table_name: "public.products",         check_type: "great_expectations", passed: false, details: "12 rows with null category",           executed_at: ago(0, 8)  },
  // analytics tables — healthy
  { check_name: "revenue must be non-negative",     table_name: "analytics.daily_revenue", check_type: "soda",              passed: true,  details: null,                                    executed_at: ago(0, 15) },
  { check_name: "No duplicate date entries",        table_name: "analytics.daily_revenue", check_type: "custom_sql",        passed: true,  details: null,                                    executed_at: ago(0, 15) },
  { check_name: "user_id must not be null",         table_name: "analytics.user_events",   check_type: "soda",              passed: true,  details: null,                                    executed_at: ago(0, 12) },
  { check_name: "event_type must not be null",      table_name: "analytics.user_events",   check_type: "soda",              passed: true,  details: null,                                    executed_at: ago(0, 12) },
  { check_name: "timestamp must not be null",       table_name: "analytics.user_events",   check_type: "great_expectations", passed: true,  details: null,                                    executed_at: ago(0, 12) },
];

// ---------------------------------------------------------------------------
// GET /schema/diff/{table}?limit=50 — combined for all tables
// ---------------------------------------------------------------------------
export const DEMO_SCHEMA_DIFFS = {
  "public.orders": [
    { column_name: "amount",        change_type: "type_changed", old_value: "decimal(10,2)", new_value: "decimal(14,4)", detected_at: ago(24) },
    { column_name: "discount_code", change_type: "added",        old_value: null,            new_value: "varchar(50)",  detected_at: ago(72) },
  ],
  "public.customers": [
    { column_name: "legacy_segment", change_type: "removed", old_value: "text", new_value: null, detected_at: ago(6) },
  ],
};

// ---------------------------------------------------------------------------
// GET /webhooks/airflow  →  { logs: [...] }
// ---------------------------------------------------------------------------
const DAG_NAMES = [
  "orders_sync_hourly",
  "marketing_etl_daily",
  "customer_refresh_daily",
  "revenue_aggregation_daily",
  "user_events_streaming",
];
export const DEMO_AIRFLOW_LOGS = {
  logs: Array.from({ length: 20 }, (_, i) => {
    const dag = DAG_NAMES[i % DAG_NAMES.length];
    const failed = (dag === "orders_sync_hourly" && i < 4) || (i % 13 === 0);
    const startH = i * 0.7;
    return {
      dag_id:           dag,
      run_id:           `run_${String(i).padStart(3, "0")}`,
      state:            failed ? "failed" : "success",
      start_time:       ago(startH + 0.05),
      end_time:         ago(startH),
      duration_seconds: Math.round(120 + Math.random() * 1400),
      received_at:      ago(startH),
    };
  }),
};

// ---------------------------------------------------------------------------
// GET /suppress/
// ---------------------------------------------------------------------------
export const DEMO_SUPPRESSIONS = [
  {
    id: 1,
    table_name: "analytics.daily_revenue",
    suppressed_until: new Date(now.getTime() + 4 * 3600_000).toISOString(),
    reason: "Planned warehouse maintenance — batch backfill in progress",
    created_at: ago(1),
  },
];

// ---------------------------------------------------------------------------
// POST /profiling/run  (demo returns pre-built profile)
// ---------------------------------------------------------------------------
export const DEMO_PROFILES = {
  "public.orders": {
    table: "public.orders",
    columns_profiled: 5,
    profiles: [
      { column: "order_id",    null_pct: 0.3,  distinct_count: 999,  min_value: "ORD-0",   max_value: "ORD-999"  },
      { column: "customer_id", null_pct: 0.0,  distinct_count: 100,  min_value: "CUST-0",  max_value: "CUST-99"  },
      { column: "amount",      null_pct: 0.0,  distinct_count: 892,  min_value: "10.12",   max_value: "499.87"   },
      { column: "status",      null_pct: 0.0,  distinct_count: 2,    min_value: "completed", max_value: "processing" },
      { column: "updated_at",  null_pct: 0.0,  distinct_count: 987,  min_value: "2024-01-09", max_value: "2024-01-15" },
    ],
  },
  default: {
    table: "demo_table",
    columns_profiled: 3,
    profiles: [
      { column: "id",         null_pct: 0.0,  distinct_count: 1000, min_value: "1",    max_value: "1000"  },
      { column: "value",      null_pct: 2.1,  distinct_count: 847,  min_value: "0.01", max_value: "9999.99" },
      { column: "created_at", null_pct: 0.0,  distinct_count: 998,  min_value: "2024-01-01", max_value: "2024-01-15" },
    ],
  },
};

// ---------------------------------------------------------------------------
// mockApiFetch — drop-in replacement for apiFetch in demo mode
// ---------------------------------------------------------------------------
export function mockApiFetch(path) {
  // Simulate a small network delay so the UI feels realistic
  return new Promise((resolve) => {
    setTimeout(() => {
      if (path === "/" || path.startsWith("/healthz"))
        resolve({ status: "demo" });
      else if (path.startsWith("/status"))
        resolve(DEMO_STATUS);
      else if (path.startsWith("/freshness"))
        resolve(DEMO_FRESHNESS);
      else if (path.startsWith("/checks/results"))
        resolve(DEMO_CHECKS);
      else if (path.startsWith("/schema/diff/")) {
        const table = decodeURIComponent(path.replace("/schema/diff/", "").split("?")[0]);
        resolve(DEMO_SCHEMA_DIFFS[table] || []);
      } else if (path.startsWith("/webhooks/airflow"))
        resolve(DEMO_AIRFLOW_LOGS);
      else if (path.startsWith("/suppress"))
        resolve(DEMO_SUPPRESSIONS);
      else if (path.startsWith("/profiling")) {
        // Extract table name from query string
        const qs = path.includes("?") ? path.split("?")[1] : "";
        const params = new URLSearchParams(qs);
        const table = params.get("table_name") || "";
        resolve(DEMO_PROFILES[table] || DEMO_PROFILES.default);
      } else
        resolve({});
    }, 280);
  });
}
