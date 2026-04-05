"""
ObservaKit — Config Loader
Loads kit.yml and expands ${VAR:-default} env var substitutions that
PyYAML silently ignores.
"""

import os
import re
from typing import Any

import yaml

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")


def _expand_env_vars(value: Any) -> Any:
    """Recursively expand ${VAR:-default} patterns in strings."""
    if isinstance(value, str):
        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            default_val = match.group(2) if match.group(2) is not None else ""
            return os.getenv(var_name, default_val)
        return _ENV_VAR_PATTERN.sub(replacer, value)
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


def load_config(path: str = "config/kit.yml") -> dict:
    """
    Load and parse kit.yml, expanding all ${VAR:-default} env var references.

    Example:
        config = load_config()
        slack_url = config["alerts"]["slack"]["webhook_url"]
        # → reads SLACK_WEBHOOK_URL from environment
    """
    try:
        with open(path, "r") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {path}")
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in config file {path}: {e}")
    return _expand_env_vars(raw)
