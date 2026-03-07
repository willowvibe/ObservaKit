"""
ObservaKit — API Key Authentication Middleware
Protects mutating endpoints with a simple API key.
"""

import logging
import os
from typing import Optional

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)):
    """
    Verify the API key from the X-API-Key header.
    If OBSERVAKIT_API_KEY is not set, authentication is disabled (dev mode).
    """
    expected_key = os.getenv("OBSERVAKIT_API_KEY")

    # If no API key is configured, skip authentication (dev mode)
    if not expected_key:
        return None

    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing API key. Set X-API-Key header.",
        )

    return api_key
