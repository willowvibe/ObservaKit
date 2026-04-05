"""
ObservaKit — API Key Authentication Middleware
Protects mutating endpoints with a simple API key.
"""

import hashlib
import logging
import os
from typing import Optional

from fastapi import HTTPException, Security, Request, Depends
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session

from backend.models import get_db, ApiKey, Project

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Security(API_KEY_HEADER),
    db: Session = Depends(get_db)
):
    """
    Verify the API key:
    1. Check for legacy OBSERVAKIT_API_KEY (superadmin).
    2. Check the database for a hashed match.
    3. If neither, fallback to DEV MODE (if configured).
    """
    expected_legacy_key = os.getenv("OBSERVAKIT_API_KEY")

    if expected_legacy_key and api_key == expected_legacy_key:
        request.state.user_role = "super_admin"
        request.state.project_id = None
        return api_key

    if api_key:
        hashed = hashlib.sha256(api_key.encode()).hexdigest()
        db_key = db.query(ApiKey).filter(ApiKey.hashed_key == hashed, ApiKey.is_active == True).first()
        if db_key:
            request.state.user_role = db_key.role
            request.state.project_id = db_key.project_id
            return api_key

    # Dev mode fallback
    if not expected_legacy_key and db.query(ApiKey).count() == 0:
        logger.warning("No API keys found and OBSERVAKIT_API_KEY is not set. Allowing access (DEV MODE).")
        request.state.user_role = "super_admin"
        request.state.project_id = None
        return None

    raise HTTPException(
        status_code=403,
        detail="Invalid or missing API key. Set X-API-Key header.",
    )


async def require_admin(request: Request, _=Depends(verify_api_key)):
    """Dependency that ensures the authenticated user has an admin role."""
    role = getattr(request.state, "user_role", None)
    if role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")
