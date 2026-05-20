# app/routers/upload.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.security import HTTPBearer
from app.config.log.log_config import get_logger
from app.services.upload_service import UploadService
from app.config.helper.jwt_helper import verify_tokens
from app.schemas.token import TokenData

router = APIRouter(prefix="/upload", tags=["upload"])
logger = get_logger("upload_router")
upload_service = UploadService()
security = HTTPBearer()


@router.post("/pdf")
async def upload_pdf(
    file: UploadFile = File(...), user_data: TokenData = Depends(verify_tokens)
):
    """Upload PDF file (Admin/Doctor only)"""
    try:
        route = router.prefix + "/pdf"

        # Extract role and user_id from token
        role = getattr(user_data, "role", None)
        if not role:
            roles = getattr(user_data, "roles", [])
            role = roles[0] if isinstance(roles, list) and roles else None
        if not role:
            raise HTTPException(status_code=403, detail="No role found in token")

        user_id = getattr(user_data, "user_id", None)
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in token")

        logger.info(
            f"Route: {route} | User: {getattr(user_data, 'sub', 'Unknown')} | Role: {role} | User ID: {user_id}"
        )

        result = await upload_service.upload_pdf(file, role, user_id)
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])

        logger.info(f"PDF upload successful: {file.filename}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in upload_pdf endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/cleanup")
async def cleanup_files(user_data: TokenData = Depends(verify_tokens)):
    """Clean up old uploaded files (Admin only)"""
    try:
        role = getattr(user_data, "role", None)
        if not role or role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

        removed_count = upload_service.cleanup_old_files()
        return {"status": "success", "message": f"Removed {removed_count} old files"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in cleanup endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
