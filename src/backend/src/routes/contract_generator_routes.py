"""AI contract generator endpoints.

POST /api/contract-generator/preview  → inspect + LLM call, return draft contract (no DB write)
POST /api/contract-generator/generate → preview + persist as a draft DataContract
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from src.common.authorization import PermissionChecker
from src.common.dependencies import DBSessionDep
from src.common.features import FeatureAccessLevel
from src.common.manager_dependencies import (
    get_contract_generator_manager,
    get_data_contracts_manager,
)
from src.controller.contract_generator_manager import ContractGeneratorManager
from src.controller.data_contracts_manager import DataContractsManager
from src.common.logging import get_logger

router = APIRouter(prefix="/api/contract-generator", tags=["contract-generator"])
logger = get_logger(__name__)


class GenerateRequest(BaseModel):
    catalog: str = Field(..., min_length=1, description="Unity Catalog catalog name")
    schema_: str = Field(..., min_length=1, alias="schema", description="Schema name")
    table: str = Field(..., min_length=1, description="Table name")
    sample_size: int = Field(20, ge=1, le=200, description="Rows to sample for LLM context")
    force: bool = Field(False, description="Regenerate even if a contract for this table already exists")

    model_config = {"populate_by_name": True}


def _user_token(x_forwarded_access_token: Optional[str]) -> Optional[str]:
    return x_forwarded_access_token or None


@router.post("/preview")
async def preview_contract(
    body: GenerateRequest,
    gen: ContractGeneratorManager = Depends(get_contract_generator_manager),
    x_forwarded_access_token: Optional[str] = Header(default=None),
    _: bool = Depends(PermissionChecker('data-contracts', FeatureAccessLevel.READ_WRITE)),
):
    """Generate a draft contract and return it WITHOUT persisting."""
    try:
        result = gen.generate(
            catalog=body.catalog,
            schema=body.schema_,
            table=body.table,
            sample_size=body.sample_size,
            user_token=_user_token(x_forwarded_access_token),
        )
    except RuntimeError as e:
        logger.warning(f"Contract generation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "contract": result.contract,
        "llm_model": result.llm_model,
        "duration_seconds": result.duration_seconds,
        "steps": result.steps,
        "warnings": result.warnings,
    }


@router.post("/generate", status_code=201)
async def generate_and_save(
    body: GenerateRequest,
    request: Request,
    db: DBSessionDep,
    gen: ContractGeneratorManager = Depends(get_contract_generator_manager),
    x_forwarded_access_token: Optional[str] = Header(default=None),
    _: bool = Depends(PermissionChecker('data-contracts', FeatureAccessLevel.READ_WRITE)),
):
    """Generate a draft contract and persist it."""
    try:
        current_user = None
        # Best-effort extract username from request state (set by auth middleware if present).
        user = getattr(request.state, "user", None)
        if user:
            current_user = getattr(user, "username", None) or getattr(user, "email", None)
        result = gen.generate_and_save(
            db=db,
            catalog=body.catalog,
            schema=body.schema_,
            table=body.table,
            sample_size=body.sample_size,
            current_user=current_user,
            user_token=_user_token(x_forwarded_access_token),
            force=body.force,
        )
    except RuntimeError as e:
        logger.warning(f"Contract generation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Contract generation failed")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
    return result


def register_routes(app):
    """Standard registration entrypoint used by app.py."""
    app.include_router(router)
