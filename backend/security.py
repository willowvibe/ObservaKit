"""
Security utilities for ObservaKit.

Provides safe identifier validation and SQL injection prevention.
"""

import re


# Maximum length for table/column identifiers to prevent abuse
MAX_IDENTIFIER_LENGTH = 64

# List of reserved SQL keywords that cannot be used as identifiers
RESERVED_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE", "DROP", "CREATE",
    "ALTER", "TRUNCATE", "UNION", "JOIN", "INNER", "LEFT", "RIGHT", "FULL",
    "ON", "AND", "OR", "NOT", "IN", "LIKE", "BETWEEN", "EXISTS", "DISTINCT",
    "GROUP", "ORDER", "HAVING", "LIMIT", "OFFSET", "VALUES", "INTO", "VALUES",
    "SET", "CASE", "WHEN", "ELSE", "END", "AS", "IS", "NULL", "TRUE", "FALSE",
    "COUNT", "SUM", "AVG", "MAX", "MIN", "CAST", "CONVERT", "COALESCE",
    "NULLIF", "DATE", "TIME", "TIMESTAMP", "INTERVAL", "YEAR", "MONTH", "DAY",
    "HOUR", "MINUTE", "SECOND", "WITH", "RECURSIVE", "VIEW", "TABLE", "COLUMN",
    "INDEX", "SEQUENCE", "TRIGGER", "FUNCTION", "PROCEDURE", "DATABASE", "SCHEMA",
    "ROLE", "GRANT", "REVOKE", "COMMIT", "ROLLBACK", "SAVEPOINT", "TRANSACTION",
    "BEGIN", "WORK", "LOCK", "TABLES", "SYNONYM", "TYPE", "DOMAIN", "CAST",
    "ALL", "ANY", "SOME", "EXCEPT", "INTERSECT", "MINUS", "MAX", "MIN", "SUM",
    "AVG", "COUNT", "TOP", "FETCH", "NEXT", "FIRST", "ONLY", "SPLIT_PART",
    "ARRAY", "JSON", "JSONB", "XML", "TEXT", "VARCHAR", "CHAR", "INTEGER",
    "BIGINT", "SMALLINT", "DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "BOOLEAN",
    "DATE", "DATETIME", "TIMESTAMP", "TIME", "INTERVAL", "YEAR", "MONTH",
    "DAY", "HOUR", "MINUTE", "SECOND", "AUTO_INCREMENT", "DEFAULT", "PRIMARY",
    "KEY", "FOREIGN", "REFERENCE", "CHECK", "CONSTRAINT", "UNIQUE", "NOT",
    "NULL", "ASC", "DESC", "NULLS", "FIRST", "LAST", "EXCLUDE", "PARTITION",
    "OVER", "RANGE", "ROWS", "GROUPS", "UNBOUNDED", "PRECEDING", "FOLLOWING",
    "EXTRACT", "DATE_PART", "EXTRACT", "CURRENT_DATE", "CURRENT_TIME",
    "CURRENT_TIMESTAMP", "CURRENT_USER", "SESSION_USER", "SYSTEM_USER",
    "LOCALTIME", "LOCALTIMESTAMP", "VERSION", "REPLACE", "REPEAT", "REPLACE",
    "IF", "THEN", "ELSE", "ENDIF", "ENDIF", "LOOP", "ENDLOOP", "WHILE",
    "ENDWHILE", "FOR", "ENDFOR", "RETURN", "OUTER", "CROSS", "NATURAL",
    "USING", "NATURAL", "LEFT", "RIGHT", "FULL", "INNER", "OUTER", "CROSS",
    "APPLY", "PIVOT", "UNPIVOT", "LATERAL", "TABLESAMPLE", "BERNOULLI",
    "SYSTEM", "PERCENT", "REPEATABLE", "ONLY", "DEFAULT", "CASCADE", "LOCAL",
    "SESSION", "TRANSACTION", "CONCURRENTLY", "DEFERRABLE", "INITIALLY",
    "IMMEDIATE", "DEFERRED", "SET", "LOCAL", "GLOBAL", "TEMP", "TEMPORARY",
    "UNLOGGED", "EXTERNAL", "CATALOG", "PRESERVE", "RESTART", "CONTINUE",
    "NESTED", "LEVEL", "READ", "WRITE", "COMMIT", "ROLLBACK", "SAVEPOINT",
    "CONNECT", "TERMINATE", "PURGE", "RELEASE", "PREPARE", "EXECUTE",
    "DEALLOCATE", "DESCRIBE", "EXPLAIN", "ANALYZE", "VERBOSE", "COSTS",
    "BUFFERS", "TIMINGS", "FORMAT", "TEXT", "XML", "JSON", "YAML", "TREE",
}


def is_safe_identifier(name: str) -> bool:
    """
    Validate that a table or column name is a safe SQL identifier.

    Checks:
    - Length is within bounds
    - Only contains alphanumeric characters and underscores
    - Does not contain SQL keywords orReserved words
    - Does not contain path traversal or special characters

    Args:
        name: The identifier to validate

    Returns:
        True if the identifier is safe, False otherwise
    """
    if not name or not isinstance(name, str):
        return False

    # Trim whitespace
    name = name.strip()

    # Check length
    if len(name) == 0 or len(name) > MAX_IDENTIFIER_LENGTH:
        return False

    # Check for path traversal or special characters
    if ".." in name or "/" in name or "\\" in name or ";" in name or "'" in name:
        return False

    # Check for SQL injection patterns
    if re.search(r'[\r\n]', name):
        return False

    # Only allow alphanumeric and underscore
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        return False

    # Check against reserved keywords (case-insensitive)
    if name.upper() in RESERVED_KEYWORDS:
        return False

    return True


def is_safe_table_reference(table: str) -> bool:
    """
    Validate a table reference (may include catalog.schema.table or schema.table).

    Args:
        table: The table reference string

    Returns:
        True if all identifier parts are safe, False otherwise
    """
    if not table or not isinstance(table, str):
        return False

    table = table.strip()

    # Split on dots to handle multi-part names
    parts = table.split(".")

    for part in parts:
        part = part.strip()
        if not is_safe_identifier(part):
            return False

    return True


def get_qualified_table_name(table: str, default_catalog: str = None, default_schema: str = None) -> str:
    """
    Validate and normalize a table reference, adding catalog/schema if needed.

    Args:
        table: The table reference (may be just table, or schema.table, or catalog.schema.table)
        default_catalog: Default catalog if not specified
        default_schema: Default schema if not specified

    Returns:
        The fully qualified table name if valid

    Raises:
        ValueError: If the table reference is invalid
    """
    if not is_safe_table_reference(table):
        raise ValueError(f"Invalid table reference: {table}")

    parts = table.split(".")

    if len(parts) == 1:
        # Just table name - add default schema
        if default_schema:
            return f"{default_schema}.{parts[0]}"
        return table
    elif len(parts) == 2:
        # schema.table or catalog.schema
        if default_catalog:
            # Assume first part is schema if we have a default catalog
            return f"{default_catalog}.{parts[0]}.{parts[1]}"
        return table
    elif len(parts) == 3:
        # catalog.schema.table - fully qualified
        return table
    else:
        raise ValueError(f"Invalid table reference format: {table}")


def safe_quote_identifier(name: str) -> str:
    """
    Safely quote a SQL identifier for use in a query.

    Note: This should only be used AFTER validation with is_safe_identifier().

    For PostgreSQL: uses double quotes
    For other databases, this may need adjustment

    Args:
        name: The identifier to quote

    Returns:
        The quoted identifier
    """
    if not is_safe_identifier(name):
        raise ValueError(f"Cannot quote unsafe identifier: {name}")

    # Escape double quotes within the identifier
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def safe_quote_table(table: str) -> str:
    """
    Safely quote a table name for use in a query.

    Args:
        table: The table reference

    Returns:
        The fully qualified and quoted table name
    """
    if not is_safe_table_reference(table):
        raise ValueError(f"Cannot quote unsafe table reference: {table}")

    parts = table.split(".")
    return ".".join(safe_quote_identifier(p) for p in parts)
