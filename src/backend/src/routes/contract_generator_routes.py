"""AI contract generator endpoints.

POST /api/contract-generator/preview  → inspect + LLM call, return draft contract (no DB write)
POST /api/contract-generator/generate → preview + persist as a draft DataContract
"""
import json
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
    except ValueError as e:
        # Identifier validation failure or similar bad-input from the manager.
        raise HTTPException(status_code=422, detail=str(e))
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
    except ValueError as e:
        # Identifier validation failure or similar bad-input from the manager.
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        logger.warning(f"Contract generation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Contract generation failed")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
    return result


@router.post("/stream")
async def stream_contract(
    body: GenerateRequest,
    request: Request,
    db: DBSessionDep,
    gen: ContractGeneratorManager = Depends(get_contract_generator_manager),
    x_forwarded_access_token: Optional[str] = Header(default=None),
    _: bool = Depends(PermissionChecker('data-contracts', FeatureAccessLevel.READ_WRITE)),
):
    """Stream contract-drafting progress as Server-Sent Events.

    Yields the generator's stage checklist + the LLM tokens live, then a terminal
    ``result`` (or ``exists`` / ``error``) event. Consumed by the Ask Ontos copilot
    panel. The SSE ``event:`` field carries the event type (stage|token|result|
    exists|error) and ``data:`` is the JSON payload.
    """
    import anyio
    from sse_starlette.sse import EventSourceResponse

    user_token = _user_token(x_forwarded_access_token)
    current_user = None
    user = getattr(request.state, "user", None)
    if user:
        current_user = getattr(user, "username", None) or getattr(user, "email", None)

    async def event_publisher():
        # Bounded buffer gives natural backpressure: the worker thread blocks on
        # send() when the client is slow; closing the receive end on disconnect
        # makes the blocked send raise (no deadlock).
        send_stream, receive_stream = anyio.create_memory_object_stream(max_buffer_size=200)

        def _run_blocking():
            try:
                for ev in gen.generate_stream(
                    catalog=body.catalog,
                    schema=body.schema_,
                    table=body.table,
                    sample_size=body.sample_size,
                    user_token=user_token,
                    db=db,
                    current_user=current_user,
                    force=body.force,
                ):
                    anyio.from_thread.run(send_stream.send, ev)
            except Exception as e:  # never let the worker die silently
                logger.exception("Contract stream generation failed")
                try:
                    anyio.from_thread.run(send_stream.send, {"type": "error", "message": str(e)})
                except Exception:
                    pass
            finally:
                anyio.from_thread.run(send_stream.aclose)

        async with anyio.create_task_group() as tg:
            tg.start_soon(anyio.to_thread.run_sync, _run_blocking)
            async with receive_stream:
                async for ev in receive_stream:
                    if await request.is_disconnected():
                        break
                    yield {"event": ev.get("type", "message"), "data": json.dumps(ev)}

    return EventSourceResponse(
        event_publisher(),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def register_routes(app):
    """Standard registration entrypoint used by app.py."""
    app.include_router(router)
