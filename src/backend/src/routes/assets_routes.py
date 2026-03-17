from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request

from src.models.assets import (
    AssetTypeCreate, AssetTypeUpdate, AssetTypeRead, AssetTypeSummary,
    AssetCreate, AssetUpdate, AssetRead, AssetSummary,
    AssetRelationshipCreate, AssetRelationshipRead,
    PaginatedAssetSummary,
    DeletePreviewItem, CascadeDeleteRequest, CascadeDeleteResult,
)
from src.controller.assets_manager import assets_manager
from src.common.authorization import PermissionChecker
from src.common.features import FeatureAccessLevel
from src.common.dependencies import (
    DBSessionDep,
    CurrentUserDep,
    AuditManagerDep,
    AuditCurrentUserDep,
)
from src.common.errors import NotFoundError, ConflictError, ValidationError
from src.common.logging import get_logger

logger = get_logger(__name__)

asset_types_router = APIRouter(prefix="/api/asset-types", tags=["Asset Types"])
assets_router = APIRouter(prefix="/api/assets", tags=["Assets"])
FEATURE_ID = "assets"


def get_assets_manager():
    return assets_manager


# ===================== Asset Types =====================

@asset_types_router.post(
    "",
    response_model=AssetTypeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.READ_WRITE))],
)
def create_asset_type(
    request: Request,
    type_in: AssetTypeCreate,
    db: DBSessionDep,
    audit_manager: AuditManagerDep,
    current_user: AuditCurrentUserDep,
    manager=Depends(get_assets_manager),
):
    """Creates a new asset type."""
    success = False
    details = {"params": {"name": type_in.name}}
    created_id = None
    try:
        result = manager.create_asset_type(db=db, type_in=type_in, current_user_id=current_user.email)
        success = True
        created_id = str(result.id)
        return result
    except ConflictError as e:
        details["exception"] = {"type": "ConflictError", "message": str(e)}
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create asset type '%s'", type_in.name)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create asset type")
    finally:
        if created_id:
            details["created_resource_id"] = created_id
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="CREATE_ASSET_TYPE", success=success, details=details,
        )


@asset_types_router.get(
    "",
    response_model=List[AssetTypeRead],
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.READ_ONLY))],
)
def get_all_asset_types(
    db: DBSessionDep,
    manager=Depends(get_assets_manager),
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = Query(None),
    type_status: Optional[str] = Query(None, alias="status"),
):
    """Lists all asset types."""
    return manager.get_all_asset_types(db=db, skip=skip, limit=limit, category=category, status=type_status)


@asset_types_router.get(
    "/summary",
    response_model=List[AssetTypeSummary],
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.READ_ONLY))],
)
def get_asset_types_summary(
    db: DBSessionDep,
    manager=Depends(get_assets_manager),
):
    """Gets a summary list of asset types for dropdowns."""
    return manager.get_asset_types_summary(db=db)


@asset_types_router.get(
    "/{type_id}",
    response_model=AssetTypeRead,
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.READ_ONLY))],
)
def get_asset_type(
    type_id: UUID,
    db: DBSessionDep,
    manager=Depends(get_assets_manager),
):
    """Gets a specific asset type by ID."""
    result = manager.get_asset_type(db=db, type_id=type_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset type '{type_id}' not found")
    return result


@asset_types_router.put(
    "/{type_id}",
    response_model=AssetTypeRead,
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.READ_WRITE))],
)
def update_asset_type(
    type_id: UUID,
    request: Request,
    type_in: AssetTypeUpdate,
    db: DBSessionDep,
    audit_manager: AuditManagerDep,
    current_user: AuditCurrentUserDep,
    manager=Depends(get_assets_manager),
):
    """Updates an existing asset type."""
    success = False
    details = {"params": {"type_id": str(type_id)}}
    try:
        result = manager.update_asset_type(db=db, type_id=type_id, type_in=type_in, current_user_id=current_user.email)
        success = True
        return result
    except NotFoundError as e:
        details["exception"] = {"type": "NotFoundError", "message": str(e)}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictError as e:
        details["exception"] = {"type": "ConflictError", "message": str(e)}
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.exception("Failed to update asset type %s", type_id)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update asset type")
    finally:
        if success:
            details["updated_resource_id"] = str(type_id)
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="UPDATE_ASSET_TYPE", success=success, details=details,
        )


@asset_types_router.delete(
    "/{type_id}",
    response_model=AssetTypeRead,
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.ADMIN))],
)
def delete_asset_type(
    type_id: UUID,
    request: Request,
    db: DBSessionDep,
    audit_manager: AuditManagerDep,
    current_user: AuditCurrentUserDep,
    manager=Depends(get_assets_manager),
):
    """Deletes an asset type. Requires Admin. Fails if assets still reference it."""
    success = False
    details = {"params": {"type_id": str(type_id)}}
    try:
        result = manager.delete_asset_type(db=db, type_id=type_id)
        success = True
        return result
    except NotFoundError as e:
        details["exception"] = {"type": "NotFoundError", "message": str(e)}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictError as e:
        details["exception"] = {"type": "ConflictError", "message": str(e)}
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.exception("Failed to delete asset type %s", type_id)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete asset type")
    finally:
        if success:
            details["deleted_resource_id"] = str(type_id)
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="DELETE_ASSET_TYPE", success=success, details=details,
        )


# ===================== Assets =====================

@assets_router.post(
    "",
    response_model=AssetRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.READ_WRITE))],
)
def create_asset(
    request: Request,
    asset_in: AssetCreate,
    db: DBSessionDep,
    audit_manager: AuditManagerDep,
    current_user: AuditCurrentUserDep,
    manager=Depends(get_assets_manager),
):
    """Creates a new asset."""
    success = False
    details = {"params": {"name": asset_in.name, "type_id": str(asset_in.asset_type_id)}}
    created_id = None
    try:
        result = manager.create_asset(db=db, asset_in=asset_in, current_user_id=current_user.email)
        success = True
        created_id = str(result.id)
        return result
    except NotFoundError as e:
        details["exception"] = {"type": "NotFoundError", "message": str(e)}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        details["exception"] = {"type": "ValidationError", "message": str(e)}
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ConflictError as e:
        details["exception"] = {"type": "ConflictError", "message": str(e)}
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create asset '%s'", asset_in.name)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create asset")
    finally:
        if created_id:
            details["created_resource_id"] = created_id
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="CREATE_ASSET", success=success, details=details,
        )


@assets_router.get(
    "",
    response_model=PaginatedAssetSummary,
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.READ_ONLY))],
)
def get_all_assets(
    db: DBSessionDep,
    manager=Depends(get_assets_manager),
    skip: int = 0,
    limit: int = 100,
    asset_type_id: Optional[UUID] = Query(None),
    asset_type_names: Optional[str] = Query(None, description="Comma-separated asset type names"),
    platform: Optional[str] = Query(None),
    domain_id: Optional[str] = Query(None),
    asset_status: Optional[str] = Query(None, alias="status"),
    name: Optional[str] = Query(None),
):
    """Lists all assets with optional filters. Returns paginated results."""
    type_names_list = [t.strip() for t in asset_type_names.split(",")] if asset_type_names else None
    return manager.get_all_assets(
        db=db, skip=skip, limit=limit,
        asset_type_id=asset_type_id, asset_type_names=type_names_list,
        platform=platform, domain_id=domain_id, status=asset_status, name=name,
    )


@assets_router.get(
    "/{asset_id}",
    response_model=AssetRead,
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.READ_ONLY))],
)
def get_asset(
    asset_id: UUID,
    db: DBSessionDep,
    manager=Depends(get_assets_manager),
):
    """Gets a specific asset by ID with relationships."""
    result = manager.get_asset(db=db, asset_id=asset_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found")
    return result


@assets_router.put(
    "/{asset_id}",
    response_model=AssetRead,
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.READ_WRITE))],
)
def update_asset(
    asset_id: UUID,
    request: Request,
    asset_in: AssetUpdate,
    db: DBSessionDep,
    audit_manager: AuditManagerDep,
    current_user: AuditCurrentUserDep,
    manager=Depends(get_assets_manager),
):
    """Updates an existing asset."""
    success = False
    details = {"params": {"asset_id": str(asset_id)}}
    try:
        result = manager.update_asset(db=db, asset_id=asset_id, asset_in=asset_in, current_user_id=current_user.email)
        success = True
        return result
    except NotFoundError as e:
        details["exception"] = {"type": "NotFoundError", "message": str(e)}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        details["exception"] = {"type": "ValidationError", "message": str(e)}
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ConflictError as e:
        details["exception"] = {"type": "ConflictError", "message": str(e)}
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.exception("Failed to update asset %s", asset_id)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update asset")
    finally:
        if success:
            details["updated_resource_id"] = str(asset_id)
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="UPDATE_ASSET", success=success, details=details,
        )


@assets_router.get(
    "/{asset_id}/infer-schema",
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.READ_ONLY))],
)
def infer_schema_from_asset(
    asset_id: UUID,
    db: DBSessionDep,
    manager=Depends(get_assets_manager),
):
    """Extract ODCS-compatible schema objects from an asset and its children."""
    try:
        return manager.infer_schema_from_asset(db=db, asset_id=asset_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Failed to infer schema from asset %s", asset_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to infer schema from asset")


@assets_router.get(
    "/{asset_id}/delete-preview",
    response_model=DeletePreviewItem,
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.ADMIN))],
)
def get_delete_preview(
    asset_id: UUID,
    db: DBSessionDep,
    manager=Depends(get_assets_manager),
):
    """Returns a tree of the asset and all hierarchical descendants that would be cascade-deleted."""
    try:
        return manager.get_delete_preview(db=db, asset_id=asset_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Failed to build delete preview for asset %s", asset_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to build delete preview")


@assets_router.post(
    "/cascade-delete",
    response_model=CascadeDeleteResult,
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.ADMIN))],
)
def cascade_delete_assets(
    body: CascadeDeleteRequest,
    request: Request,
    db: DBSessionDep,
    audit_manager: AuditManagerDep,
    current_user: AuditCurrentUserDep,
    manager=Depends(get_assets_manager),
):
    """Deletes multiple assets in leaf-first order. Requires Admin."""
    details = {"params": {"asset_ids": [str(aid) for aid in body.asset_ids]}}
    try:
        result = manager.cascade_delete_assets(
            db=db, asset_ids=body.asset_ids, current_user_id=current_user.email,
        )
        details["deleted_count"] = len(result.deleted)
        details["failed_count"] = len(result.failed)
        return result
    except Exception as e:
        logger.exception("Failed to cascade-delete assets")
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cascade-delete assets")
    finally:
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="CASCADE_DELETE_ASSETS",
            success="exception" not in details, details=details,
        )


@assets_router.delete(
    "/{asset_id}",
    response_model=AssetRead,
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.ADMIN))],
)
def delete_asset(
    asset_id: UUID,
    request: Request,
    db: DBSessionDep,
    audit_manager: AuditManagerDep,
    current_user: AuditCurrentUserDep,
    manager=Depends(get_assets_manager),
):
    """Deletes an asset. Requires Admin."""
    success = False
    details = {"params": {"asset_id": str(asset_id)}}
    try:
        result = manager.delete_asset(db=db, asset_id=asset_id, current_user_id=current_user.email)
        success = True
        return result
    except NotFoundError as e:
        details["exception"] = {"type": "NotFoundError", "message": str(e)}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Failed to delete asset %s", asset_id)
        details["exception"] = {"type": type(e).__name__, "message": str(e)}
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete asset")
    finally:
        if success:
            details["deleted_resource_id"] = str(asset_id)
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="DELETE_ASSET", success=success, details=details,
        )


# ===================== Asset Relationships =====================

@assets_router.post(
    "/relationships",
    response_model=AssetRelationshipRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.READ_WRITE))],
)
def add_asset_relationship(
    request: Request,
    rel_in: AssetRelationshipCreate,
    db: DBSessionDep,
    audit_manager: AuditManagerDep,
    current_user: AuditCurrentUserDep,
    manager=Depends(get_assets_manager),
):
    """Creates a relationship between two assets."""
    success = False
    details = {"params": {"source": str(rel_in.source_asset_id), "target": str(rel_in.target_asset_id), "type": rel_in.relationship_type}}
    try:
        result = manager.add_relationship(db=db, rel_in=rel_in, current_user_id=current_user.email)
        success = True
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.exception("Failed to add asset relationship")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add relationship")
    finally:
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="ADD_RELATIONSHIP", success=success, details=details,
        )


@assets_router.delete(
    "/relationships/{relationship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(PermissionChecker(FEATURE_ID, FeatureAccessLevel.READ_WRITE))],
)
def remove_asset_relationship(
    relationship_id: UUID,
    request: Request,
    db: DBSessionDep,
    audit_manager: AuditManagerDep,
    current_user: AuditCurrentUserDep,
    manager=Depends(get_assets_manager),
):
    """Removes a relationship between assets."""
    success = False
    details = {"params": {"relationship_id": str(relationship_id)}}
    try:
        manager.remove_relationship(db=db, relationship_id=relationship_id)
        success = True
        return None
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Failed to remove asset relationship")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove relationship")
    finally:
        audit_manager.log_action(
            db=db, username=current_user.username,
            ip_address=request.client.host if request.client else None,
            feature=FEATURE_ID, action="REMOVE_RELATIONSHIP", success=success, details=details,
        )


def register_routes(app):
    app.include_router(asset_types_router)
    app.include_router(assets_router)
    logger.info("Asset routes registered with prefix /api/asset-types, /api/assets")
