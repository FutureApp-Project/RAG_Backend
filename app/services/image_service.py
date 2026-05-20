# app/services/image_service.py
import pytesseract
from PIL import Image
import io
import base64
import cv2
import numpy as np
import re
from typing import Dict, Any, Optional, List
import requests
from app.config.log.log_config import get_logger

logger = get_logger("image_service")


class ImageService:
    def __init__(self):
        # Initialize Tesseract for text extraction (still useful for some cases)
        try:
            pytesseract.pytesseract.tesseract_cmd = (
                r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            )
            logger.info("Tesseract OCR initialized")
        except:
            logger.warning("Tesseract OCR not found, text extraction will be limited")

        # Medical image analysis model (using pre-trained or custom model)
        self.skin_conditions = [
            "acne",
            "eczema",
            "psoriasis",
            "rosacea",
            "dermatitis",
            "ringworm",
            "hives",
            "shingles",
            "melanoma",
            "vitiligo",
        ]

        self.scalp_conditions = [
            "dandruff",
            "seborrheic_dermatitis",
            "psoriasis",
            "alopecia",
            "folliculitis",
            "head_lice",
            "tinea_capitis",
        ]

        logger.info("ImageService initialized with medical analysis capabilities")

    def _decode_image_bytes(self, base64_string: str) -> bytes:
        """Decode a base64 image payload into raw bytes."""
        if "," in base64_string:
            base64_string = base64_string.split(",", 1)[1]
        return base64.b64decode(base64_string)

    def analyze_image_features(self, base64_string: str) -> Dict[str, Any]:
        """Infer whether an image is more likely scalp or skin using simple visual heuristics."""
        try:
            image_bytes = self._decode_image_bytes(base64_string)
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                raise ValueError("Could not decode image")

            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            edges = cv2.Canny(gray, 50, 150)
            edge_density = float(np.sum(edges > 0) / edges.size)

            _, threshold = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            flake_percentage = float(np.sum(threshold > 0) / threshold.size)

            scalp_visibility = float(self._estimate_scalp_visibility(img))
            inflammation_indicator = float(self._detect_inflammation(img))
            saturation = float(np.mean(hsv[:, :, 1]))

            contains_hair = edge_density > 0.09 or scalp_visibility > 0.18
            likely_scalp = contains_hair or flake_percentage > 0.015
            likely_skin = (
                not likely_scalp and inflammation_indicator > 0.003 and saturation > 35
            )

            return {
                "contains_hair": contains_hair,
                "likely_scalp": likely_scalp,
                "likely_skin": likely_skin,
                "edge_density": edge_density,
                "flake_percentage": flake_percentage,
                "scalp_visibility": scalp_visibility,
                "inflammation_indicator": inflammation_indicator,
                "suggested_image_type": "scalp" if likely_scalp else "skin",
            }
        except Exception as e:
            logger.warning(f"Image feature analysis failed: {str(e)}")
            return {
                "contains_hair": False,
                "likely_scalp": False,
                "likely_skin": True,
                "suggested_image_type": "skin",
                "error": str(e),
            }

    def extract_text_from_image(self, image_bytes: bytes) -> str:
        """Extract text from image using OCR (for text-based images)"""
        try:
            logger.info("Extracting text from image using OCR")
            image = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(image)
            return text.strip()
        except Exception as e:
            logger.warning(f"OCR text extraction failed: {str(e)}")
            return ""

    def analyze_medical_image(
        self, image_bytes: bytes, image_type: str = "skin"
    ) -> Dict[str, Any]:
        """Analyze medical images (skin rashes, scalp conditions, etc.)"""
        try:
            logger.info(f"Analyzing {image_type} medical image")

            # Convert bytes to OpenCV image
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                raise ValueError("Could not decode image")

            # Basic image analysis
            analysis = self._perform_image_analysis(img, image_type)

            # Simulate ML model prediction (in production, use actual trained model)
            predictions = self._simulate_condition_prediction(img, image_type)

            # Get recommendations based on analysis
            recommendations = self._generate_recommendations(predictions, image_type)

            logger.info(
                f"Image analysis completed. Conditions detected: {len(predictions)}"
            )

            return {
                "image_type": image_type,
                "analysis": analysis,
                "detected_conditions": predictions,
                "recommendations": recommendations,
                "severity_estimate": self._estimate_severity(predictions),
                "confidence_level": "medium",  # Simulated confidence
            }

        except Exception as e:
            logger.error(f"Error analyzing medical image: {str(e)}")
            return {
                "image_type": image_type,
                "error": str(e),
                "detected_conditions": [],
                "recommendations": [
                    "Please consult a dermatologist for accurate diagnosis"
                ],
            }

    def _perform_image_analysis(self, img, image_type: str) -> Dict[str, Any]:
        """Perform basic image analysis"""
        try:
            # Convert to HSV for better color analysis
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

            # Calculate basic statistics
            brightness = np.mean(img)
            saturation = np.mean(hsv[:, :, 1])

            # Edge detection for pattern analysis
            edges = cv2.Canny(img, 100, 200)
            edge_density = np.sum(edges > 0) / edges.size

            # Color distribution
            hsv_hist = cv2.calcHist([hsv], [0, 1], None, [180, 256], [0, 180, 0, 256])

            analysis = {
                "image_dimensions": f"{img.shape[1]}x{img.shape[0]}",
                "brightness": float(brightness),
                "saturation": float(saturation),
                "edge_density": float(edge_density),
                "color_variation": float(np.std(hsv_hist)),
                "aspect_ratio": img.shape[1] / img.shape[0],
            }

            # Additional analysis based on image type
            if image_type == "skin":
                analysis.update(self._analyze_skin_image(img, hsv))
            elif image_type == "scalp":
                analysis.update(self._analyze_scalp_image(img, hsv))

            return analysis

        except Exception as e:
            logger.error(f"Error in image analysis: {str(e)}")
            return {"error": str(e)}

    def _analyze_skin_image(self, img, hsv) -> Dict[str, Any]:
        """Specific analysis for skin images"""
        # Color ranges for different skin conditions
        # Note: These are simplified examples
        redness_mask = cv2.inRange(hsv, np.array([0, 50, 50]), np.array([10, 255, 255]))
        redness_percentage = np.sum(redness_mask > 0) / redness_mask.size

        # Analyze texture using GLCM or other methods
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        texture_variance = np.var(gray)

        return {
            "redness_percentage": float(redness_percentage * 100),
            "texture_variance": float(texture_variance),
            "skin_tone_category": self._categorize_skin_tone(hsv),
            "lesion_count_estimate": self._estimate_lesion_count(img),
        }

    def _analyze_scalp_image(self, img, hsv) -> Dict[str, Any]:
        """Specific analysis for scalp/hair images"""
        # Analyze for dandruff, flakes, etc.
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Simple thresholding for flake detection
        _, threshold = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        flake_percentage = np.sum(threshold > 0) / threshold.size

        # Hair density estimation (simplified)
        edges = cv2.Canny(gray, 50, 150)
        hair_density = np.sum(edges > 0) / edges.size

        return {
            "flake_percentage": float(flake_percentage * 100),
            "hair_density": float(hair_density),
            "scalp_visibility": float(self._estimate_scalp_visibility(img)),
            "inflammation_indicator": float(self._detect_inflammation(img)),
        }

    def _simulate_condition_prediction(
        self, img, image_type: str
    ) -> List[Dict[str, Any]]:
        """Simulate ML model predictions (replace with actual model in production)"""
        predictions = []

        if image_type == "skin":
            # Simulate skin condition predictions
            conditions = self.skin_conditions[:3]  # Top 3 most likely
            for condition in conditions:
                confidence = np.random.uniform(0.3, 0.9)
                if confidence > 0.5:  # Only include if confidence > 50%
                    predictions.append(
                        {
                            "condition": condition.replace("_", " ").title(),
                            "confidence": round(confidence, 2),
                            "description": self._get_condition_description(condition),
                            "common_symptoms": self._get_common_symptoms(condition),
                        }
                    )

        elif image_type == "scalp":
            # Simulate scalp condition predictions
            conditions = self.scalp_conditions[:3]
            for condition in conditions:
                confidence = np.random.uniform(0.3, 0.9)
                if confidence > 0.5:
                    predictions.append(
                        {
                            "condition": condition.replace("_", " ").title(),
                            "confidence": round(confidence, 2),
                            "description": self._get_condition_description(condition),
                            "common_symptoms": self._get_common_symptoms(condition),
                        }
                    )

        # Sort by confidence
        predictions.sort(key=lambda x: x["confidence"], reverse=True)
        return predictions

    def _generate_recommendations(
        self, predictions: List[Dict], image_type: str
    ) -> List[str]:
        """Generate medical recommendations based on predictions"""
        recommendations = []

        if not predictions:
            recommendations.append(
                "No specific conditions detected. Image appears normal."
            )
            recommendations.append(
                "Monitor for any changes and consult if symptoms persist."
            )
            return recommendations

        # General recommendations
        recommendations.append("Based on image analysis, possible conditions detected.")
        recommendations.append("This analysis is for informational purposes only.")

        # Specific recommendations based on conditions
        for pred in predictions[:2]:  # Top 2 conditions
            condition = pred["condition"].lower()

            if "dandruff" in condition or "seborrheic" in condition:
                recommendations.append(
                    "For dandruff: Try anti-dandruff shampoos with ketoconazole or selenium sulfide."
                )
                recommendations.append(
                    "Avoid harsh hair products and wash hair regularly."
                )

            elif "psoriasis" in condition:
                recommendations.append(
                    "For psoriasis: Consult dermatologist for topical treatments."
                )
                recommendations.append(
                    "Consider phototherapy or systemic treatments for severe cases."
                )

            elif "eczema" in condition or "dermatitis" in condition:
                recommendations.append(
                    "For eczema: Use moisturizers regularly and avoid triggers."
                )
                recommendations.append(
                    "Topical corticosteroids may help reduce inflammation."
                )

            elif "acne" in condition:
                recommendations.append(
                    "For acne: Maintain good hygiene and avoid touching affected areas."
                )
                recommendations.append(
                    "Consider topical retinoids or benzoyl peroxide treatments."
                )

        # Always include these
        recommendations.append(
            "Consult a dermatologist for accurate diagnosis and treatment."
        )
        recommendations.append(
            "Take clear photos in good lighting for better analysis."
        )
        recommendations.append("Note any itching, pain, or changes in appearance.")

        return recommendations

    def _estimate_severity(self, predictions: List[Dict]) -> str:
        """Estimate severity based on predictions"""
        if not predictions:
            return "none"

        avg_confidence = sum(p["confidence"] for p in predictions) / len(predictions)

        if avg_confidence > 0.8:
            return "high"
        elif avg_confidence > 0.6:
            return "moderate"
        else:
            return "low"

    # Helper methods
    def _categorize_skin_tone(self, hsv) -> str:
        """Categorize skin tone (simplified)"""
        avg_hue = np.mean(hsv[:, :, 0])
        if avg_hue < 15:
            return "fair"
        elif avg_hue < 30:
            return "light"
        elif avg_hue < 45:
            return "medium"
        else:
            return "dark"

    def _estimate_lesion_count(self, img) -> int:
        """Estimate number of lesions/spots (simplified)"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        return min(len(contours), 20)  # Cap at 20 for simplicity

    def _estimate_scalp_visibility(self, img) -> float:
        """Estimate how much scalp is visible"""
        # Simplified implementation
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        scalp_color = np.percentile(gray, 10)  # Darker areas might be scalp
        scalp_mask = gray < scalp_color * 1.2
        return float(np.sum(scalp_mask) / scalp_mask.size)

    def _detect_inflammation(self, img) -> float:
        """Detect inflammation (redness)"""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        redness_mask = cv2.inRange(
            hsv, np.array([0, 100, 100]), np.array([10, 255, 255])
        )
        return float(np.sum(redness_mask > 0) / redness_mask.size)

    def _get_condition_description(self, condition: str) -> str:
        """Get description for a medical condition"""
        descriptions = {
            "dandruff": "Flaking of the scalp skin, often with itching",
            "seborrheic_dermatitis": "Inflammatory skin condition affecting scalp",
            "psoriasis": "Autoimmune condition causing thick, scaly patches",
            "acne": "Skin condition with pimples, blackheads, and inflammation",
            "eczema": "Itchy, inflamed skin often with redness and dryness",
            "ringworm": "Fungal infection causing ring-shaped rash",
            "alopecia": "Hair loss condition",
            "melanoma": "Serious form of skin cancer",
        }
        return descriptions.get(
            condition, "Skin/scalp condition requiring medical evaluation"
        )

    def _get_common_symptoms(self, condition: str) -> List[str]:
        """Get common symptoms for a condition"""
        symptoms = {
            "dandruff": ["white flakes", "itchy scalp", "dryness"],
            "seborrheic_dermatitis": ["red skin", "greasy scales", "itching"],
            "psoriasis": ["silvery scales", "red patches", "dry skin"],
            "acne": ["pimples", "blackheads", "redness", "inflammation"],
        }
        return symptoms.get(condition, ["itching", "redness", "skin changes"])

    def process_base64_image(
        self,
        base64_string: str,
        analyze_medical: bool = False,
        image_type: str = "skin",
    ) -> Dict[str, Any]:
        """Process base64 encoded image with optional medical analysis"""
        try:
            image_bytes = self._decode_image_bytes(base64_string)

            if analyze_medical:
                # Perform medical image analysis
                return self.analyze_medical_image(image_bytes, image_type)
            else:
                # Extract text (fallback)
                text = self.extract_text_from_image(image_bytes)
                return {
                    "text_extracted": text,
                    "analysis_available": False,
                    "message": "Image processed for text extraction only",
                }

        except Exception as e:
            logger.error(f"Error processing base64 image: {str(e)}")
            return {"error": str(e), "message": "Failed to process image"}
