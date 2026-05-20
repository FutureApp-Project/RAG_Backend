# app/services/local_model_service.py
from typing import Dict, Any, Optional
import ollama
import asyncio
from concurrent.futures import ThreadPoolExecutor
from app.config.log.log_config import get_logger
import os
from dotenv import load_dotenv

load_dotenv()


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


# Load configuration from environment
MAX_OUTPUT_LENGTH = int(os.getenv("MAX_OUTPUT_LENGTH", "800"))
RESPONSE_TIMEOUT = int(os.getenv("RESPONSE_TIMEOUT", "30"))
OLLAMA_MODEL = _get_required_env("OLLAMA_MODEL")

OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
OLLAMA_TOP_K = int(os.getenv("OLLAMA_TOP_K", "20"))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.8"))
OLLAMA_REPEAT_PENALTY = float(os.getenv("OLLAMA_REPEAT_PENALTY", "1.2"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "1024"))
OLLAMA_NUM_BATCH = int(os.getenv("OLLAMA_NUM_BATCH", "32"))
OLLAMA_MAX_PREDICT = int(os.getenv("OLLAMA_MAX_PREDICT", "160"))

logger = get_logger("local_model_service")
logger.info(
    f"Configuration loaded: MAX_OUTPUT_LENGTH={MAX_OUTPUT_LENGTH}, RESPONSE_TIMEOUT={RESPONSE_TIMEOUT}, OLLAMA_MODEL={OLLAMA_MODEL}, OLLAMA_TEMPERATURE={OLLAMA_TEMPERATURE}, OLLAMA_TOP_K={OLLAMA_TOP_K}, OLLAMA_TOP_P={OLLAMA_TOP_P}, OLLAMA_REPEAT_PENALTY={OLLAMA_REPEAT_PENALTY}, OLLAMA_NUM_CTX={OLLAMA_NUM_CTX}, OLLAMA_NUM_BATCH={OLLAMA_NUM_BATCH}, OLLAMA_MAX_PREDICT={OLLAMA_MAX_PREDICT}"
)


class LocalModelService:
    def __init__(self):
        # Flexible system prompt that encourages complete sentences
        self.system_prompt = """You are a medical information assistant. You ONLY answer medical and health-related questions.
IMPORTANT RULES:
1. Always respond in the SAME language as the user's question. If the question is in German, respond in German. If in English, respond in English.
2. Do NOT include any internal reasoning or thinking in your response. Only output the final answer.
3. You MUST only provide medical, health, and wellness information. If a question is not related to medicine or health, respond with: "I can only answer medical and health-related questions. Please ask a medical question."
4. NEVER provide religious, political, or non-medical interpretations of medical terms.
5. If the question contains a medical term (like cancer, diabetes, etc.), always interpret it in a medical context regardless of how the question is phrased.
Format your response professionally. Ensure every sentence is complete and ends with proper punctuation."""

        self.executor = ThreadPoolExecutor(max_workers=1)
        self.timeout = RESPONSE_TIMEOUT
        self.model = OLLAMA_MODEL

        logger.info(
            f"LocalModelService initialized with model={self.model}, timeout={self.timeout}s, max_output={MAX_OUTPUT_LENGTH}"
        )

    def _call_ollama_sync(self, messages: list, options: dict) -> dict:
        """Synchronous Ollama call for thread executor"""
        try:
            logger.debug(f"Calling Ollama with model: {self.model}")
            response = ollama.chat(model=self.model, messages=messages, options=options)
            logger.debug("Ollama call successful")
            return response
        except Exception as e:
            logger.error(f"Ollama sync call failed: {str(e)}")
            raise

    def _ensure_complete_sentences(self, text: str) -> str:
        """Ensure the text ends with complete sentences"""
        if not text:
            return text

        # Split into sentences (rough approximation)
        sentences = []
        current = ""

        for char in text:
            current += char
            if char in [".", "!", "?"]:
                # Check if this looks like a complete sentence (has at least a few words)
                if len(current.strip().split()) >= 3:
                    sentences.append(current.strip())
                    current = ""

        # If we have any complete sentences, join them
        if sentences:
            return " ".join(sentences)

        # If no complete sentences found but we have text, try to find last complete sentence
        # by looking for punctuation
        last_period = text.rfind(".")
        last_excl = text.rfind("!")
        last_ques = text.rfind("?")
        last_punct = max(last_period, last_excl, last_ques)

        if last_punct > 0:
            return text[: last_punct + 1].strip()

        # If still no punctuation, return as is but ensure it ends with punctuation
        if text and text[-1] not in [".", "!", "?"]:
            return text + "."

        return text

    async def generate_response(
        self,
        query: str,
        image_analysis: Optional[Dict] = None,
        image_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate response from local model with configurable length"""
        try:
            logger.info(f"Local model generating response for query: {query[:100]}")

            # Build prompt based on what's being asked
            if image_analysis:
                # Serialize the full analysis dict into readable text
                analysis_parts = []
                for cond in image_analysis.get("detected_conditions", []):
                    if isinstance(cond, dict):
                        name = cond.get("condition", "Unknown")
                        conf = cond.get("confidence", 0)
                        desc = cond.get("description", "")
                        analysis_parts.append(f"{name} ({conf:.0%}): {desc}")
                severity = image_analysis.get("severity_estimate", "")
                if severity:
                    analysis_parts.append(f"Severity: {severity}")
                recs = image_analysis.get("recommendations", [])
                if recs:
                    analysis_parts.append(f"Recommendations: {'; '.join(recs[:3])}")
                analysis_text = (
                    "\n".join(analysis_parts)
                    if analysis_parts
                    else "No specific findings"
                )
                full_prompt = f"{query}\n\nImage analysis results:\n{analysis_text}"
            else:
                full_prompt = query

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": full_prompt},
            ]

            # Calculate appropriate token limit (roughly 4 chars per token)
            # Add extra budget for model thinking tokens that get stripped later
            token_limit = min(OLLAMA_MAX_PREDICT, max(96, MAX_OUTPUT_LENGTH // 6 + 64))

            options = {
                "temperature": OLLAMA_TEMPERATURE,
                "num_predict": token_limit,
                "num_ctx": OLLAMA_NUM_CTX,
                "num_batch": OLLAMA_NUM_BATCH,
                "top_k": OLLAMA_TOP_K,
                "top_p": OLLAMA_TOP_P,
                "repeat_penalty": OLLAMA_REPEAT_PENALTY,
                "stop": ["User:", "\n\nUser", "\nHuman:", "\n\nHuman"],
            }

            # Call Ollama with timeout
            loop = asyncio.get_event_loop()
            try:
                logger.info(f"Calling Ollama with model {self.model}")
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        self.executor, self._call_ollama_sync, messages, options
                    ),
                    timeout=self.timeout,
                )

                response_text = response["message"]["content"].strip()
                logger.info(f"Ollama response received: {len(response_text)} chars")

                # Strip model thinking tokens (MedGemma <unused94>thought, DeepSeek <think>)
                import re

                response_text = re.sub(
                    r"<unused\d+>thought\s.*?(?=\n\n|$)",
                    "",
                    response_text,
                    flags=re.DOTALL,
                ).strip()
                response_text = re.sub(
                    r"<think>.*?</think>", "", response_text, flags=re.DOTALL
                ).strip()
                response_text = re.sub(r"<unused\d+>", "", response_text).strip()
                logger.info(f"After thinking-token cleanup: {len(response_text)} chars")

                # Check if response is meaningful
                if not response_text or len(response_text.split()) < 5:
                    logger.info("Local model returned very short response")
                    return {
                        "success": False,
                        "response": "",
                        "confidence": 0.0,
                        "error": "response_too_short",
                    }

                # Ensure complete sentences
                response_text = self._ensure_complete_sentences(response_text)

                # Only truncate if significantly over limit and preserve sentence boundaries
                if len(response_text) > MAX_OUTPUT_LENGTH * 1.2:
                    # Truncate at the last complete sentence within limit
                    truncated = response_text[:MAX_OUTPUT_LENGTH]
                    last_period = truncated.rfind(".")
                    last_excl = truncated.rfind("!")
                    last_ques = truncated.rfind("?")
                    last_punct = max(last_period, last_excl, last_ques)

                    if last_punct > 0:
                        response_text = truncated[: last_punct + 1].strip()
                    else:
                        # If no punctuation found, find last space to avoid word break
                        last_space = truncated.rfind(" ")
                        if last_space > 0:
                            response_text = truncated[:last_space] + "..."
                        else:
                            response_text = truncated + "..."

                logger.info(
                    f"Local model response successful: {len(response_text)} chars"
                )

                # Compute confidence score based on response quality
                confidence = self._compute_confidence(query, response_text)
                logger.info(f"Computed confidence: {confidence:.2f}")

                return {
                    "success": True,
                    "response": response_text,
                    "confidence": confidence,
                }

            except asyncio.TimeoutError:
                logger.info(f"Local model timed out after {self.timeout} seconds")
                return {
                    "success": False,
                    "response": "",
                    "confidence": 0.0,
                    "error": "timeout",
                }

        except ollama.ResponseError as e:
            logger.error(f"Ollama response error: {str(e)}", exc_info=True)
            return {
                "success": False,
                "response": "",
                "confidence": 0.0,
                "error": f"ollama_error: {str(e)}",
            }
        except Exception as e:
            logger.error(f"Local model error: {str(e)}", exc_info=True)
            return {
                "success": False,
                "response": "",
                "confidence": 0.0,
                "error": str(e),
            }

    def _compute_confidence(self, query: str, response: str) -> float:
        """
        Compute a confidence score for the local model response based on:
        - Response length adequacy
        - Sentence completeness
        - Query-response keyword overlap
        - Absence of hedging/uncertainty language
        """
        score = 0.5  # Base score

        # 1. Length adequacy (0 to +0.15)
        word_count = len(response.split())
        if word_count >= 30:
            score += 0.15
        elif word_count >= 15:
            score += 0.10
        elif word_count >= 8:
            score += 0.05

        # 2. Sentence completeness (0 to +0.10)
        if response.rstrip().endswith((".", "!", "?")):
            score += 0.10

        # 3. Query-response relevance via keyword overlap (0 to +0.15)
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "have",
            "has",
            "had",
            "do",
            "does",
            "what",
            "how",
            "why",
            "which",
            "can",
            "could",
            "would",
            "should",
            "die",
            "der",
            "das",
            "und",
            "ist",
            "sind",
            "ein",
            "eine",
            "zu",
            "für",
            "von",
            "mit",
            "auf",
            "an",
            "in",
            "was",
            "wie",
            "bitte",
            "ich",
            "sie",
        }
        query_words = set(query.lower().split()) - stop_words
        response_words = set(response.lower().split()) - stop_words
        if query_words:
            overlap = len(query_words & response_words) / len(query_words)
            score += min(overlap * 0.20, 0.15)

        # 4. Penalize hedging/uncertainty language (-0.05 to -0.15)
        hedging = [
            "i think",
            "possibly",
            "might be",
            "not sure",
            "uncertain",
            "i cannot",
            "i can't",
            "unclear",
            "vielleicht",
            "unsicher",
            "ich weiss nicht",
            "keine ahnung",
        ]
        hedging_count = sum(1 for h in hedging if h in response.lower())
        score -= min(hedging_count * 0.05, 0.15)

        # 5. Bonus for medical terminology (+0.05)
        medical_terms = [
            "diagnosis",
            "symptom",
            "treatment",
            "condition",
            "patient",
            "clinical",
            "therapy",
            "medication",
            "disease",
            "chronic",
            "diagnose",
            "symptom",
            "behandlung",
            "therapie",
            "erkrankung",
            "medikament",
            "krankheit",
        ]
        if any(t in response.lower() for t in medical_terms):
            score += 0.05

        return max(0.1, min(score, 0.95))
