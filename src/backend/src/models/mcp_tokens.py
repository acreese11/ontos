"""
Pydantic models for MCP tokens API.

Models for creating, reading, and managing MCP API tokens.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MCPTokenCreate(BaseModel):
    """Request model for creating a new MCP token.

    MCP tokens are for service-principal/M2M callers only - a script,
    scheduled job, or external automation with no human to act on behalf of.
    Human callers should use forwarded-identity (OBO) auth instead, which is
    gated by their real Ontos permissions automatically; there is no way to
    mint a token that impersonates a human's access. See
    docs/notes/MCP_AUTH_REWORK_PRD.md. Also: this path cannot be used behind a
    Unity Catalog HTTP connection (only direct/bespoke HTTP callers) - see
    PRD §4.2.
    """
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable name for the token")
    scopes: List[str] = Field(default=[], description="List of allowed scopes (e.g., ['data-products:read'])")
    expires_days: Optional[int] = Field(default=90, ge=1, le=365, description="Days until expiration (null for no expiration)")
    is_service_principal: bool = Field(
        default=True,
        description=(
            "Must be true - MCP tokens are for service-principal/M2M callers only. "
            "Human callers should use forwarded-identity (OBO) auth instead."
        ),
    )


class MCPTokenResponse(BaseModel):
    """Response model for a created token (includes plaintext token once)."""
    id: UUID
    name: str
    token: str = Field(..., description="The plaintext token - save this, it won't be shown again")
    scopes: List[str]
    is_service_principal: bool
    created_at: datetime
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


class MCPTokenInfo(BaseModel):
    """Response model for token information (without the actual token)."""
    id: UUID
    name: str
    scopes: List[str]
    is_service_principal: bool
    created_by: Optional[str]
    created_at: datetime
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    is_active: bool
    is_expired: bool

    class Config:
        from_attributes = True


class MCPTokenList(BaseModel):
    """Response model for listing tokens."""
    tokens: List[MCPTokenInfo]
    total: int

