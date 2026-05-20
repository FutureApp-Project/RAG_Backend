import openai
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any
from app.config.log.log_config import get_logger

logger = get_logger("chatgpt_service")


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


class ChatGPTService:
    def __init__(self):
        # Initialize OpenAI client (synchronous)
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = _get_required_env("OPENAI_MODEL")
        self.executor = ThreadPoolExecutor(max_workers=2)
        logger.info("ChatGPTService initialized")

    def _call_openai_sync(self, prompt: str, system_prompt: str) -> str:
        """Synchronous OpenAI call for thread executor"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=500,
        )
        return response.choices[0].message.content

    async def generate_medical_response(
        self,
        query: str,
        image_analysis: Optional[Dict] = None,
        image_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate medical response using ChatGPT API"""
        try:
            prompt = self._build_medical_prompt(query, image_analysis, image_type)
            system_prompt = "You are a helpful medical assistant. Provide accurate, evidence-based information with appropriate disclaimers."

            loop = asyncio.get_event_loop()
            response_text = await asyncio.wait_for(
                loop.run_in_executor(
                    self.executor, self._call_openai_sync, prompt, system_prompt
                ),
                timeout=30,
            )

            if response_text:
                return {
                    "success": True,
                    "response": response_text.strip(),
                    "confidence": 0.85,
                }

            return {"success": False, "response": "", "confidence": 0.0}

        except asyncio.TimeoutError:
            logger.error("ChatGPT API timed out after 30s")
            return {
                "success": False,
                "response": "",
                "confidence": 0.0,
                "error": "timeout",
            }
        except Exception as e:
            logger.error(f"ChatGPT API error: {str(e)}")
            return {
                "success": False,
                "response": "",
                "confidence": 0.0,
                "error": str(e),
            }

    def _build_medical_prompt(
        self, query: str, image_analysis: Optional[Dict], image_type: Optional[str]
    ) -> str:
        """Build medical prompt for ChatGPT"""
        prompt = f"User query: {query}\n\n"

        if image_analysis and image_type:
            prompt += f"Image Analysis ({image_type}):\n"
            if image_analysis.get("detected_conditions"):
                for cond in image_analysis["detected_conditions"]:
                    prompt += f"- {cond['condition']} (confidence: {cond['confidence']*100:.0f}%)\n"

        prompt += "\nPlease provide helpful, evidence-based information with appropriate medical disclaimers."

        return prompt
