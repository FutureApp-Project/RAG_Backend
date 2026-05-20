#app/schemas/image.py

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

class ImageTypeEnum(str, Enum):
    SKIN = "skin"
    SCALP = "scalp"

class ImageUpload(BaseModel):
    image: str = Field(..., description="Base64 encoded image string")
    image_type: ImageTypeEnum = Field(default=ImageTypeEnum.SKIN)
    description: Optional[str] = Field(None, max_length=500)
    
    class Config:
        json_schema_extra = {
            "example": {
                "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
                "image_type": "skin",
                "description": "Red rash on arm, itchy for 3 days"
            }
        }

class DetectedCondition(BaseModel):
    condition: str
    confidence: float = Field(..., ge=0, le=1)
    description: str
    common_symptoms: List[str]

class ImageAnalysisResponse(BaseModel):
    image_type: str
    detected_conditions: List[DetectedCondition]
    recommendations: List[str]
    severity_estimate: str
    confidence_level: str
    analysis: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "image_type": "skin",
                "detected_conditions": [
                    {
                        "condition": "Eczema",
                        "confidence": 0.75,
                        "description": "Inflammatory skin condition",
                        "common_symptoms": ["itching", "redness", "dry skin"]
                    }
                ],
                "recommendations": [
                    "Use moisturizer regularly",
                    "Avoid known triggers",
                    "Consult dermatologist"
                ],
                "severity_estimate": "moderate",
                "confidence_level": "medium"
            }
        }