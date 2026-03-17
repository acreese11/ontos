from typing import Any, Dict, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class ConnectionBase(BaseModel):
    name: str = Field(..., min_length=1, description="User-friendly connection name")
    connector_type: str = Field(..., min_length=1, description="Connector type (e.g. bigquery, databricks)")
    description: Optional[str] = Field(None, description="Optional description")
    config: Dict[str, Any] = Field(default_factory=dict, description="Connector-specific configuration")
    enabled: bool = Field(True, description="Whether this connection is active")
    is_default: bool = Field(False, description="Whether this is the default for its connector type")
    system_asset_id: Optional[UUID] = Field(None, description="Linked System asset for hierarchy imports")


class ConnectionCreate(ConnectionBase):
    pass


class ConnectionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    system_asset_id: Optional[UUID] = None


class ConnectionResponse(ConnectionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

    model_config = {"from_attributes": True}


class ConnectorTypeInfo(BaseModel):
    """Metadata about an available connector type."""
    connector_type: str
    display_name: str
    description: str
    capabilities: Dict[str, bool] = Field(default_factory=dict)
    config_fields: list = Field(default_factory=list, description="Hints for the UI about what config fields exist")
