# app/services/uploadService.py
# This file can be used to implement upload-related services

import os
import shutil
from typing import Dict, Any
from fastapi import UploadFile
from app.config.log.log_config import get_logger
from app.services.vector_store_service import VectorStoreService
import uuid
from datetime import datetime

logger = get_logger("upload_service")


class UploadService:
    def __init__(self):
        self.vector_store = VectorStoreService()
        self.upload_dir = "./uploads"
        self.processed_dir = "./processed_pdfs"

        # Create directories if they don't exist
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)

        logger.info(f"UploadService initialized")
        logger.info(f"Upload directory: {self.upload_dir}")
        logger.info(f"Processed directory: {self.processed_dir}")
        if not self.vector_store.available:
            logger.warning(
                "Upload service started with unavailable vector store: %s",
                self.vector_store.initialization_error,
            )

    async def upload_pdf(
        self, file: UploadFile, user_role: str, user_id: int
    ) -> Dict[str, Any]:
        """Upload, save, and process PDF file into vector database"""
        try:
            logger.info(
                f"PDF upload request from user_id: {user_id}, role: {user_role}"
            )

            if not self.vector_store.available:
                logger.error(
                    "Rejected PDF upload because vector store is unavailable: %s",
                    self.vector_store.initialization_error,
                )
                return {
                    "status": "error",
                    "message": "Document processing is temporarily unavailable. Please try again later.",
                }

            # Check if user has permission
            if user_role not in ["admin", "doctor"]:
                logger.warning(
                    f"Unauthorized upload attempt by user_id: {user_id}, role: {user_role}"
                )
                return {
                    "status": "error",
                    "message": "Only admin and doctor can upload PDFs",
                }

            # Validate file type
            if not file.filename.lower().endswith(".pdf"):
                logger.warning(f"Invalid file type: {file.filename}")
                return {"status": "error", "message": "Only PDF files are allowed"}

            # Validate file size (max 20MB)
            MAX_FILE_SIZE = int(os.getenv("MAX_UPLOAD_SIZE_MB", "20")) * 1024 * 1024
            file_content = await file.read()
            if len(file_content) > MAX_FILE_SIZE:
                logger.warning(
                    f"File too large: {len(file_content)} bytes (max {MAX_FILE_SIZE})"
                )
                return {
                    "status": "error",
                    "message": f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB",
                }
            await file.seek(0)  # Reset file position for subsequent read

            # Validate PDF magic bytes
            if not file_content[:5] == b"%PDF-":
                logger.warning(f"Invalid PDF file (bad magic bytes): {file.filename}")
                return {
                    "status": "error",
                    "message": "File does not appear to be a valid PDF",
                }

            # Generate unique filename to avoid conflicts
            original_filename = file.filename
            file_extension = original_filename.split(".")[-1]
            unique_filename = f"{uuid.uuid4().hex}.{file_extension}"

            # Save uploaded file temporarily
            temp_filepath = os.path.join(self.upload_dir, unique_filename)

            logger.info(f"Saving uploaded file to: {temp_filepath}")
            try:
                with open(temp_filepath, "wb") as buffer:
                    content = await file.read()
                    buffer.write(content)
            except OSError as e:
                logger.error("Failed to save uploaded PDF: %s", str(e), exc_info=True)
                return {
                    "status": "error",
                    "message": "Failed to save uploaded file",
                }

            file_size = os.path.getsize(temp_filepath)
            logger.info(f"File saved successfully. Size: {file_size} bytes")

            # Prepare metadata
            metadata = {
                "uploaded_by": user_id,
                "user_role": user_role,
                "original_filename": original_filename,
                "upload_date": datetime.now().isoformat(),
                "file_size": file_size,
            }

            # Process PDF and convert to vectors
            logger.info(f"Starting vector conversion for: {original_filename}")
            vector_result = self.vector_store.upload_pdf(temp_filepath, metadata)

            if vector_result["status"] == "success":
                # Move processed file to permanent location
                permanent_filename = f"processed_{original_filename}"
                permanent_path = os.path.join(self.processed_dir, permanent_filename)

                # Keep a copy in processed directory
                try:
                    shutil.copy2(temp_filepath, permanent_path)
                except OSError as e:
                    logger.error(
                        "Failed to copy processed PDF: %s", str(e), exc_info=True
                    )
                    return {
                        "status": "error",
                        "message": "PDF was processed but could not be archived",
                    }

                # Remove temporary file
                try:
                    os.remove(temp_filepath)
                except OSError:
                    logger.warning(
                        "Could not remove temporary upload file: %s", temp_filepath
                    )

                logger.info(
                    f"PDF successfully processed and converted to vectors: {original_filename}"
                )

                # Get collection stats
                stats = self.vector_store.get_collection_stats()

                return {
                    "status": "success",
                    "message": "PDF uploaded and converted to vectors successfully",
                    "original_filename": original_filename,
                    "processed_filename": permanent_filename,
                    "vector_result": vector_result,
                    "collection_stats": stats,
                    "metadata": metadata,
                }
            else:
                # Remove temporary file if processing failed
                if os.path.exists(temp_filepath):
                    os.remove(temp_filepath)

                logger.error(
                    f"Vector conversion failed: {vector_result.get('message', 'Unknown error')}"
                )
                return vector_result

        except Exception as e:
            logger.error(f"Error uploading PDF: {str(e)}", exc_info=True)

            # Cleanup on error
            temp_filepath = os.path.join(
                self.upload_dir,
                unique_filename if "unique_filename" in locals() else "unknown",
            )
            if os.path.exists(temp_filepath):
                try:
                    os.remove(temp_filepath)
                except OSError:
                    logger.warning(
                        "Could not remove temporary upload file after error: %s",
                        temp_filepath,
                    )

            return {"status": "error", "message": f"Error processing PDF: {str(e)}"}

    def get_uploaded_files(self, user_role: str) -> Dict[str, Any]:
        """Get list of uploaded and processed files"""
        try:
            if user_role not in ["admin", "doctor"]:
                return {"status": "error", "message": "Access denied"}

            uploaded_files = []
            if os.path.exists(self.processed_dir):
                for filename in os.listdir(self.processed_dir):
                    filepath = os.path.join(self.processed_dir, filename)
                    if os.path.isfile(filepath) and filename.lower().endswith(".pdf"):
                        file_stats = os.stat(filepath)
                        uploaded_files.append(
                            {
                                "filename": filename,
                                "size": file_stats.st_size,
                                "modified": datetime.fromtimestamp(
                                    file_stats.st_mtime
                                ).isoformat(),
                            }
                        )

            # Get vector database stats
            vector_stats = self.vector_store.get_collection_stats()

            logger.info(f"Retrieved {len(uploaded_files)} processed files")

            return {
                "status": "success",
                "uploaded_files": uploaded_files,
                "vector_database": vector_stats,
            }

        except Exception as e:
            logger.error(f"Error getting uploaded files: {str(e)}")
            return {"status": "error", "message": str(e)}

    def delete_uploaded_file(self, filename: str, user_role: str) -> Dict[str, Any]:
        """Delete an uploaded file and its vectors"""
        try:
            if user_role not in ["admin"]:
                return {"status": "error", "message": "Only admin can delete files"}

            # Prevent path traversal
            if ".." in filename or "/" in filename or "\\" in filename:
                return {"status": "error", "message": "Invalid filename"}

            filepath = os.path.join(self.processed_dir, filename)

            # Ensure the resolved path is within the allowed directory
            allowed_base = os.path.abspath(self.processed_dir)
            resolved_path = os.path.abspath(filepath)
            if not resolved_path.startswith(allowed_base):
                return {"status": "error", "message": "Invalid file path"}

            if not os.path.exists(resolved_path):
                return {"status": "error", "message": "File not found"}

            # Remove from vector database first
            delete_result = self.vector_store.delete_document(filepath)

            # Remove file
            os.remove(filepath)

            logger.info(f"Deleted file and vectors: {filename}")

            return {
                "status": "success",
                "message": f"File '{filename}' and its vectors deleted successfully",
                "vector_delete_result": delete_result,
            }

        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}")
            return {"status": "error", "message": str(e)}

    def cleanup_old_files(self, days_old: int = 30):
        """Clean up old uploaded files"""
        try:
            import time

            current_time = time.time()
            removed_count = 0
            days_in_seconds = days_old * 24 * 3600

            for directory in [self.upload_dir, self.processed_dir]:
                if os.path.exists(directory):
                    for filename in os.listdir(directory):
                        file_path = os.path.join(directory, filename)
                        if os.path.isfile(file_path):
                            file_age = current_time - os.path.getmtime(file_path)
                            if file_age > days_in_seconds:
                                try:
                                    # Also remove from vector database if it's a processed file
                                    if directory == self.processed_dir:
                                        self.vector_store.delete_document(file_path)

                                    os.remove(file_path)
                                    removed_count += 1
                                    logger.info(f"Removed old file: {filename}")
                                except Exception as e:
                                    logger.warning(
                                        f"Could not remove file {filename}: {str(e)}"
                                    )

            logger.info(
                f"Cleanup completed: removed {removed_count} files older than {days_old} days"
            )
            return removed_count

        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            return 0
