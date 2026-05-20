# app/routers/faq.py
import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from app.config.log.log_config import get_logger
from app.config.helper.jwt_helper import verify_tokens
from app.schemas.token import TokenData

router = APIRouter(prefix="/faq", tags=["faq"])
logger = get_logger("faq_router")

def get_faq_folder_path() -> str:
    """Get the absolute path to the FAQ folder."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    return os.path.join(project_root, "FAQ")

@router.get("/GetAllFAQFiles", response_model=List[str])
async def GetAllFAQFiles(user_data: TokenData = Depends(verify_tokens)):
    """
    Return a list of all files in the FAQ folder.
    
    Returns:
        List[str]: List of filenames in the FAQ folder
    """
    logger.info("GetAllFAQFiles endpoint called")
    
    try:
        faq_folder = get_faq_folder_path()
        logger.debug(f"FAQ folder path: {faq_folder}")
        
        # Create folder if it doesn't exist
        if not os.path.exists(faq_folder):
            logger.info(f"Creating FAQ folder: {faq_folder}")
            os.makedirs(faq_folder, exist_ok=True)
            return []  # Empty list for new folder
        
        # Get all files in the folder
        try:
            files = []
            for item in os.listdir(faq_folder):
                item_path = os.path.join(faq_folder, item)
                if os.path.isfile(item_path):
                    files.append(item)
            
            logger.info(f"Found {len(files)} FAQ file(s)")
            return sorted(files)  # Return sorted list for consistency
            
        except PermissionError:
            logger.error(f"Permission denied for FAQ folder: {faq_folder}")
            raise HTTPException(
                status_code=403, 
                detail="Permission denied accessing FAQ resources"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in GetAllFAQFiles: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail="Internal server error"
        )