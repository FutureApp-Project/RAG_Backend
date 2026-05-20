# app/services/chat_service.py

from typing import Dict, Any, Optional, List, cast
from datetime import datetime, date
import uuid
import re
import os
from dotenv import load_dotenv

from sqlalchemy import select, and_, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.log.log_config import get_logger
from app.services.vector_store_service import VectorStoreService
from app.services.audio_service import create_audio_service
from app.services.image_service import ImageService
from app.services.local_model_service import LocalModelService
from app.services.chatgpt_service import ChatGPTService
from app.config.database.database import AsyncSessionLocal
from app.models.chat_message import ChatMessage
from app.models.chat_sessions import ChatSession


load_dotenv(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
)
MAX_OUTPUT_LENGTH = int(os.getenv("MAX_OUTPUT_LENGTH", "500"))
RESPONSE_TIMEOUT = int(os.getenv("RESPONSE_TIMEOUT", "40"))
logger = get_logger("chat_service")


class ChatService:
    def __init__(self):
        self.vector_store = VectorStoreService()
        self.audio_service = create_audio_service()
        self.image_service = ImageService()
        self.local_model = LocalModelService()
        self.chatgpt = ChatGPTService()
        logger.info("ChatService initialized with medical image analysis")

    @staticmethod
    def _create_async_session() -> AsyncSession:
        """Return the configured async DB session with an explicit type for static analysis."""
        return cast(AsyncSession, AsyncSessionLocal())

    # ========== TEXT FORMATTING & CLEANING ==========

    def _format_bot_response(self, raw_text: str) -> str:
        """
        Clean and format the bot's response.
        Removes incomplete sentences, fixes formatting issues.
        """
        if not raw_text:
            return "I couldn't generate a response. Please try again."

        # Clean up common formatting issues
        cleaned_text = raw_text

        # Remove lines that are just uppercase labels (like "BEHAVIAL.")
        lines = cleaned_text.split("\n")
        filtered_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Skip lines that are just uppercase words followed by period (likely headers)
            if line.isupper() and line.endswith("."):
                continue
            # Skip very short fragmented lines
            if len(line.split()) < 3 and not line.endswith("."):
                continue
            filtered_lines.append(line)

        # Join back together
        cleaned_text = "\n".join(filtered_lines)

        # Ensure proper sentence structure
        sentences = []
        current_sentence = ""

        for line in cleaned_text.split("\n"):
            line = line.strip()
            if not line:
                if current_sentence:
                    sentences.append(current_sentence.strip())
                    current_sentence = ""
                continue

            if current_sentence and not current_sentence.endswith("."):
                current_sentence += " " + line
            else:
                if current_sentence:
                    sentences.append(current_sentence.strip())
                current_sentence = line

        if current_sentence:
            sentences.append(current_sentence.strip())

        # Filter out incomplete sentences
        complete_sentences = []
        for sentence in sentences:
            # Check if sentence looks complete
            if len(sentence.split()) >= 4 and (
                sentence.endswith(".")
                or sentence.endswith("!")
                or sentence.endswith("?")
            ):
                # Capitalize first letter
                if sentence and not sentence[0].isupper():
                    sentence = sentence[0].upper() + sentence[1:]
                complete_sentences.append(sentence)

        # If we have complete sentences, join them
        if complete_sentences:
            formatted_text = " ".join(complete_sentences)
        else:
            # Fallback: use cleaned text as-is
            formatted_text = cleaned_text

        # Ensure the response ends properly
        if not formatted_text.endswith("."):
            formatted_text += "."

        return formatted_text

    def _clean_response(self, response: str) -> str:
        """Clean up response text"""
        if not response:
            return response

        # Remove model thinking tokens (MedGemma, DeepSeek, etc.)
        # Strip <unused94>thought ... patterns
        response = re.sub(
            r"<unused\d+>thought\s.*?(?=\n\n|$)", "", response, flags=re.DOTALL
        ).strip()
        # Strip <think>...</think> blocks (DeepSeek)
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
        # Strip any remaining <unused\d+> tags
        response = re.sub(r"<unused\d+>", "", response).strip()

        # Remove quotes if present
        response = response.strip("\"'")

        # Remove redundant prefixes
        prefixes_to_remove = [
            "Answer:",
            "Antwort:",
            "Response:",
            "According to medical sources:",
            "Laut medizinischen Quellen:",
            "Here is a short answer:",
            "Hier ist eine kurze Antwort:",
        ]

        for prefix in prefixes_to_remove:
            if response.startswith(prefix):
                response = response[len(prefix) :].strip()

        # Remove excessive whitespace
        response = " ".join(response.split())

        # Ensure it ends with punctuation
        if response and response[-1] not in [".", "!", "?"]:
            response += "."

        return response

    def _format_final_response(
        self, response_text: str, query: str, lang: str, confidence: float
    ) -> str:
        """Format the final response with appropriate header and disclaimer"""

        # Add confidence indicator if confidence is low
        if confidence < 0.6:
            if lang == "de":
                prefix = "(Geringe Sicherheit) "
            else:
                prefix = "(Low confidence) "
            response_text = prefix + response_text

        # Add disclaimer
        if lang == "de":
            disclaimer = "\n\nWichtiger Hinweis: Diese Informationen stammen aus medizinischen Nachschlagewerken und dienen nur der allgemeinen Information. Ich bin kein Arzt und kann keine medizinische Beratung geben. Bei gesundheitlichen Bedenken konsultieren Sie bitte einen Arzt."
        else:
            disclaimer = "\n\nImportant: This information comes from medical reference sources and is for general knowledge only. I am not a doctor and cannot provide medical advice. For health concerns, please consult a healthcare professional."

        return response_text + disclaimer

    # ========== LANGUAGE DETECTION ==========

    def _detect_language(self, text: str) -> str:
        """Detect if text is in German or English"""
        common_german_words = [
            "der",
            "die",
            "das",
            "und",
            "ich",
            "du",
            "sie",
            "wir",
            "ist",
            "bin",
            "hast",
            "habe",
            "kann",
            "möchte",
            "bitte",
            "danke",
            "guten",
            "hallo",
        ]
        common_english_words = [
            "the",
            "and",
            "you",
            "I",
            "have",
            "has",
            "can",
            "would",
            "like",
            "what",
            "how",
            "please",
            "thank",
            "hello",
            "good",
        ]

        text_lower = text.lower()
        german_count = sum(1 for word in common_german_words if word in text_lower)
        english_count = sum(1 for word in common_english_words if word in text_lower)

        return "de" if german_count > english_count else "en"

    def _is_medical_response(self, response_text: str) -> bool:
        """Check if a response is relevant to medicine/health. Reject religious, political, etc."""
        non_medical_keywords = [
            "religious",
            "christianity",
            "christian",
            "god's will",
            "divine",
            "church",
            "bible",
            "prayer",
            "spiritual",
            "faith healing",
            "the lord",
            "jesus",
            "allah",
            "buddhist",
            "hindu",
            "political",
            "election",
            "government",
            "party",
        ]
        response_lower = response_text.lower()
        non_medical_count = sum(
            1 for kw in non_medical_keywords if kw in response_lower
        )
        if non_medical_count >= 2:
            logger.warning(
                f"Non-medical response detected ({non_medical_count} non-medical keywords)"
            )
            return False
        return True

    def _is_actionable_answer(self, response_text: str, query: str) -> bool:
        """Reject meta, prompt-echo, and clarification responses that are not actual answers."""
        if not response_text:
            return False

        response_lower = response_text.lower()
        query_lower = query.lower()

        meta_phrases = [
            "please provide the medical question",
            "the user's question",
            "the assistant's previous response",
            "previous response was",
            "question is ambiguous",
            "based on the information provided",
            "i am ready to help",
            "did not mention",
            "however, the assistant",
            "the user asked",
        ]
        if any(phrase in response_lower for phrase in meta_phrases):
            logger.warning("Rejected meta/non-answer model response")
            return False

        query_terms = set(re.findall(r"\w+", query_lower))
        if (
            query_terms
            and "question" in response_lower
            and len(query_terms.intersection(set(re.findall(r"\w+", response_lower))))
            <= 1
        ):
            logger.warning(
                "Rejected response that talks about the question instead of answering it"
            )
            return False

        return self._is_medical_response(response_text)

    def _should_include_conversation_context(self, query: str) -> bool:
        """Only include recent context for likely follow-up prompts, not fresh standalone questions."""
        query_lower = query.lower().strip()

        standalone_prefixes = [
            "what is ",
            "what are ",
            "explain ",
            "explain me about ",
            "tell me about ",
            "define ",
            "describe ",
        ]
        followup_markers = [
            "it ",
            "this ",
            "that ",
            "my image",
            "the image",
            "uploaded",
            "scalp",
            "skin",
            "dandruff",
            "dandruf",
            "rash",
            "look at",
            "but it",
        ]

        if any(query_lower.startswith(prefix) for prefix in standalone_prefixes):
            return False

        if any(marker in query_lower for marker in followup_markers):
            return True

        return len(query_lower.split()) <= 5

    def _resolve_image_type(
        self,
        image_content: str,
        requested_image_type: Optional[str],
        user_query: Optional[str],
    ) -> str:
        """Resolve scalp vs skin robustly using user hints and image features."""
        requested = (requested_image_type or "").strip().lower()
        query_lower = (user_query or "").lower()

        feature_analysis = self.image_service.analyze_image_features(image_content)
        detected = feature_analysis.get("suggested_image_type", "skin")

        scalp_hints = [
            "scalp",
            "hair",
            "dandruff",
            "dandruf",
            "seborrheic",
            "flakes",
            "itchy scalp",
        ]
        skin_hints = [
            "skin",
            "rash",
            "eczema",
            "psoriasis",
            "acne",
            "face",
            "arm",
            "leg",
        ]

        hinted_scalp = any(hint in query_lower for hint in scalp_hints)
        hinted_skin = any(hint in query_lower for hint in skin_hints)

        if hinted_scalp:
            return "scalp"
        if hinted_skin and requested != "scalp":
            return "skin"
        if requested in {"skin", "scalp"} and requested == detected:
            return requested
        if requested == "skin" and detected == "scalp":
            logger.info(
                "Overriding requested skin image_type to scalp based on feature analysis"
            )
            return "scalp"
        if requested == "scalp" and detected == "skin" and not hinted_scalp:
            logger.info(
                "Keeping requested scalp image_type despite neutral feature analysis"
            )
            return "scalp"
        if requested in {"skin", "scalp"}:
            return requested
        return detected

    # ========== VECTOR DB & RESPONSE GENERATION ==========

    def _extract_vector_content_for_refinement(
        self, query: str, vector_results: Dict
    ) -> str:
        """Extract vector content for refinement - OPTIMIZED for speed"""
        try:
            vector_data = vector_results.get("results", [])

            if not vector_data:
                return "__NO_RELEVANT_VECTOR_RESULTS__"

            # Only use top results with positive similarity
            extracted_snippets = []

            for i, result in enumerate(vector_data[:3]):
                content = result.get("content", "")
                similarity = result.get("similarity_score", 0)

                # CRITICAL FIX: Only use results with positive similarity
                if similarity <= 0.2:  # Skip negative or very low similarity
                    continue

                # Clean content
                content = content.replace("\n", " ").replace("  ", " ").strip()

                # Limit to 200 chars per snippet
                if len(content) > 10:
                    extracted_snippets.append(content[:200])

            if not extracted_snippets:
                return "__NO_RELEVANT_VECTOR_RESULTS__"

            # Return combined but limited content
            combined = " ".join(extracted_snippets)
            if len(combined) > MAX_OUTPUT_LENGTH:
                # Try to cut at the last period
                trunc = combined[:MAX_OUTPUT_LENGTH]
                last_punct = max(trunc.rfind("."), trunc.rfind("!"), trunc.rfind("?"))
                if last_punct > 0:
                    return trunc[: last_punct + 1].strip()
                return trunc.strip()
            return combined

        except Exception as e:
            logger.error(f"Error extracting vector content: {str(e)}")
            return "__VECTOR_ERROR__"

    def _is_response_relevant(self, query: str, response: str) -> bool:
        """Check if response is relevant to the query"""
        query_words = set(query.lower().split())
        response_words = set(response.lower().split())

        # Remove common stop words
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
            "die",
            "der",
            "das",
            "und",
            "oder",
            "aber",
            "in",
            "auf",
            "bei",
            "zu",
            "für",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "shall",
            "should",
            "may",
            "might",
            "must",
            "can",
            "could",
            "this",
            "that",
            "these",
            "those",
        }

        query_words = query_words - stop_words
        response_words = response_words - stop_words

        # Check for overlapping meaningful words
        overlap = query_words.intersection(response_words)

        # If response is very short but has at least one meaningful overlap
        if len(response.split()) < 30 and len(overlap) >= 1:
            return True

        # For longer responses, need more overlap
        return len(overlap) >= 2

    def _create_fallback_from_vector(self, vector_content: str, lang: str) -> str:
        """Create a simple fallback response from vector content"""
        if vector_content.startswith("__"):
            if lang == "de":
                return "Keine spezifischen Informationen verfügbar."
            else:
                return "No specific information available."

        # Try to extract the first meaningful sentence
        sentences = re.split(r"[.!?]+", vector_content)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence.split()) > 5:
                # Clean up
                sentence = sentence.split("]")[-1].strip()
                if sentence:
                    return sentence[:200] + ("..." if len(sentence) > 200 else "")

        if lang == "de":
            return "Allgemeine medizinische Informationen gefunden, aber nicht spezifisch zur Frage."
        else:
            return (
                "Found general medical information, but not specific to the question."
            )

    def _generate_response_from_vector(
        self,
        query: str,
        vector_results: Dict,
        image_analysis: Optional[Dict] = None,
        image_type: Optional[str] = None,
        lang: str = "de",
        system_prompt: str = "",
    ) -> str:
        """Generate concise response from vector database results with strict formatting"""
        try:
            # Get vector data
            vector_data = vector_results.get("results", [])

            if not vector_data:
                return "__NO_VECTOR_RESULTS__"

            # Extract and filter results by relevance
            relevant_content = []
            query_lower = query.lower()

            # Split query into key terms
            common_stop_words = {
                "what",
                "are",
                "the",
                "symptoms",
                "of",
                "for",
                "in",
                "to",
                "a",
                "an",
                "für",
                "die",
                "und",
                "ist",
                "sind",
                "zu",
                "ein",
                "eine",
                "der",
                "das",
                "explain",
                "about",
                "tell",
                "me",
                "regarding",
                "concerning",
                "please",
            }
            query_terms = set(
                word for word in query_lower.split() if word not in common_stop_words
            )

            for result in vector_data[:3]:
                content = result.get("content", "").lower()
                similarity = result.get("similarity_score", 0)

                # Skip if similarity is too low
                if similarity < -0.4:
                    continue

                # Check if content is actually relevant to the query
                matching_terms = sum(1 for term in query_terms if term in content)

                # Skip if no query terms match
                if matching_terms == 0 and len(query_terms) > 0:
                    continue

                content_original = result.get("content", "")
                if content_original and len(content_original.strip()) > 20:
                    content_original = (
                        content_original.replace("\n", " ").replace("  ", " ").strip()
                    )
                    relevant_content.append(content_original)

            if not relevant_content:
                return "__NO_RELEVANT_VECTOR_RESULTS__"

            # Combine and extract complete sentences
            combined_text = " ".join(relevant_content)
            sentences = re.split(r"(?<=[.!?])\s+", combined_text)

            # Filter for complete, relevant sentences
            filtered_sentences = []

            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue

                if len(sentence.split()) >= 3 and not sentence.startswith(
                    ("•", "-", "*", "KEY", "BEHAVIORAL", "COGNITIVE", "EMOTIONAL")
                ):
                    if sentence and not sentence[0].isupper():
                        sentence = sentence[0].upper() + sentence[1:]
                    filtered_sentences.append(sentence)

            if not filtered_sentences:
                return "__NO_RELEVANT_VECTOR_RESULTS__"

            # Take the most relevant sentences
            bullet_lines = [f"- {sentence}" for sentence in filtered_sentences[:3]]

            # Create header based on language
            if lang == "de":
                header = "Laut medizinischen Quellen:"
                disclaimer = "\n\nWichtiger Hinweis: Diese Informationen stammen aus medizinischen Nachschlagewerken und dienen nur der allgemeinen Information. Ich bin kein Arzt und kann keine medizinische Beratung geben. Bei gesundheitlichen Bedenken konsultieren Sie bitte einen Arzt."
            else:
                header = "According to medical sources:"
                disclaimer = "\n\nImportant: This information comes from medical reference sources and is for general knowledge only. I am not a doctor and cannot provide medical advice. For health concerns, please consult a healthcare professional."

            response_lines = [header]
            response_lines.extend(bullet_lines)
            response_lines.append(disclaimer)

            final_response = "\n".join(response_lines)

            # Ensure response isn't too long
            if len(final_response) > MAX_OUTPUT_LENGTH * 1.5:
                # Truncate at sentence boundary
                truncated = final_response[:MAX_OUTPUT_LENGTH]
                last_period = truncated.rfind(".")
                if last_period > 0:
                    final_response = truncated[: last_period + 1] + disclaimer
                else:
                    final_response = truncated + "..." + disclaimer

            return final_response

        except Exception as e:
            logger.error(f"Error generating vector response: {str(e)}")
            return "__VECTOR_ERROR__"

    async def _get_recent_messages(
        self, session_id: uuid.UUID, limit: int = 6
    ) -> List[Dict[str, str]]:
        """Fetch recent messages from current session for conversation context"""
        try:
            async with self._create_async_session() as session:
                result = await session.execute(
                    select(ChatMessage)
                    .where(ChatMessage.chat_session_id == session_id)
                    .order_by(ChatMessage.timestamp.desc())
                    .limit(limit)
                )
                messages = result.scalars().all()
                # Reverse to chronological order and format
                history = []
                for msg in reversed(list(messages)):
                    is_user = cast(bool, msg.is_user)
                    role = "User" if is_user else "Assistant"
                    # Truncate long messages to keep context window manageable
                    content = (cast(Optional[str], msg.content) or "")[:300]
                    if content != "":
                        history.append({"role": role, "content": content})
                return history
        except Exception as e:
            logger.warning(f"Failed to fetch recent messages: {str(e)}")
            return []

    def _build_conversation_context(
        self, history: List[Dict[str, str]], lang: str
    ) -> str:
        """Build a conversation context string from recent messages"""
        if not history:
            return ""
        lines = []
        for msg in history:
            lines.append(f"{msg['role']}: {msg['content']}")
        context = "\n".join(lines)
        if lang == "de":
            return f"\nBisheriger Gesprächsverlauf:\n{context}\n\n"
        return f"\nRecent conversation:\n{context}\n\n"

    async def _get_response_with_hierarchy(
        self,
        query: str,
        image_analysis: Optional[Dict] = None,
        image_type: Optional[str] = None,
        session_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        Intelligent query pipeline with priority-based response hierarchy:
        1. Cached Q&R pairs (Vector DB) — similarity >= 0.85 → instant return
        2. Medical document search → refine with local model → back-store
        3. Local model standalone (confidence >= 0.65) → back-store
        4. ChatGPT API → back-store
        5. Local model simplified fallback → back-store
        6. Safe fallback message
        """

        # Detect language from query
        lang = self._detect_language(query)
        logger.info(f"Detected language: {lang}")

        # Fetch conversation history for context (limit to 3 to keep prompt small)
        conversation_context = ""
        if session_id and self._should_include_conversation_context(query):
            history = await self._get_recent_messages(session_id, limit=2)
            conversation_context = self._build_conversation_context(history, lang)
            if conversation_context:
                logger.info(f"Loaded {len(history)} recent messages for context")

        # ── Step 0: Check cached query-response pairs ──
        logger.info(f"Step 0: Checking cached Q&R pairs for: {query[:100]}...")
        try:
            cached = self.vector_store.find_cached_response(query)
            if cached:
                confidence = cached.get("confidence", cached.get("similarity", 0.0))
                logger.info(
                    f"Cache HIT — confidence={confidence:.3f}, source={cached['source']}"
                )
                cached_text = cached.get("response_text", cached.get("response", ""))
                # Re-format with disclaimer (disclaimer is stripped before caching)
                formatted_response = self._format_final_response(
                    cached_text, query, lang, confidence
                )
                return {
                    "response_text": formatted_response,
                    "source": "vector_db",
                    "confidence": confidence,
                    "vector_results": None,
                }
        except Exception as e:
            logger.warning(f"Cache lookup failed: {str(e)}")

        # ── Step 1: Search medical_documents collection ──
        logger.info(f"Step 1: Searching medical documents for: {query[:100]}...")
        vector_results = self.vector_store.query(query, n_results=8)

        if vector_results and vector_results.get("results"):
            logger.info(f"Found {len(vector_results['results'])} results in vector DB")

            # Filter for relevant results, with a preference for generated knowledge
            relevant_results = []
            query_lower = query.lower()
            query_keywords = set(re.findall(r"\w+", query_lower))

            for result in vector_results.get("results", []):
                content = result.get("content", "").lower()
                stored_query = (result.get("query_text") or "").lower()
                similarity = result.get("similarity_score", 0)
                is_generated = bool(result.get("generated", False))

                content_keywords = set(re.findall(r"\w+", content))
                stored_query_keywords = set(re.findall(r"\w+", stored_query))
                overlap_count = len(query_keywords.intersection(content_keywords))
                stored_query_overlap = len(
                    query_keywords.intersection(stored_query_keywords)
                )

                if is_generated:
                    if similarity >= 0.18 and (
                        stored_query_overlap >= 1 or overlap_count >= 1
                    ):
                        result["match_score"] = (
                            similarity + 0.15 + min(stored_query_overlap, 3) * 0.05
                        )
                        relevant_results.append(result)
                elif similarity > 0.3 and overlap_count >= 1:
                    result["match_score"] = similarity + min(overlap_count, 3) * 0.03
                    relevant_results.append(result)

            if relevant_results:
                relevant_results.sort(
                    key=lambda result: (
                        bool(result.get("generated", False)),
                        result.get("match_score", result.get("similarity_score", 0)),
                    ),
                    reverse=True,
                )
                vector_results["results"] = relevant_results
                logger.info(
                    f"Found {len(relevant_results)} relevant results after filtering"
                )

                best_result = relevant_results[0]
                best_response = self._clean_response(
                    best_result.get("response_text", "")
                )
                best_similarity = best_result.get("similarity_score", 0)

                if (
                    best_result.get("generated")
                    and best_response
                    and best_similarity >= 0.18
                    and self._is_medical_response(best_response)
                ):
                    direct_confidence = max(0.65, min(best_similarity + 0.2, 0.9))
                    logger.info(
                        f"Returning generated knowledge directly from vector DB (similarity={best_similarity:.2f})"
                    )
                    return {
                        "response_text": self._format_final_response(
                            best_response, query, lang, direct_confidence
                        ),
                        "source": "vector_db_generated",
                        "confidence": direct_confidence,
                        "vector_results": vector_results,
                    }

                vector_raw_content = self._extract_vector_content_for_refinement(
                    query, vector_results
                )

                if vector_raw_content != "__NO_RELEVANT_VECTOR_RESULTS__":
                    similarities = [
                        r.get("similarity_score", 0)
                        for r in vector_results.get("results", [])
                    ]
                    confidence = max(similarities) if similarities else 0.7
                    confidence = max(0.6, min(confidence, 0.95))

                    # Refine with local model
                    logger.info("Refining vector response with local model...")

                    if lang == "de":
                        refinement_prompt = f"""Beantworte die folgende medizinische Frage in vollständigen Sätzen basierend auf den gegebenen Informationen:
{conversation_context}
    Frage: {query}

    Informationen aus medizinischen Quellen:
    {vector_raw_content}

    Antwort (vollständige Sätze, ca. {MAX_OUTPUT_LENGTH} Zeichen):"""
                    else:
                        refinement_prompt = f"""Answer the following medical question in complete sentences based on the given information:
{conversation_context}
    Question: {query}

    Information from medical sources:
    {vector_raw_content}

    Answer (complete sentences, about {MAX_OUTPUT_LENGTH} characters):"""

                    try:
                        local_refinement = await self.local_model.generate_response(
                            query=refinement_prompt,
                            image_analysis=None,
                            image_type=None,
                        )

                        if local_refinement and local_refinement.get("success"):
                            refined_response = local_refinement["response"].strip()

                            if (
                                refined_response
                                and len(refined_response.split()) >= 5
                                and self._is_actionable_answer(refined_response, query)
                            ):
                                refined_response = self._clean_response(
                                    refined_response
                                )
                                formatted_response = self._format_final_response(
                                    refined_response, query, lang, confidence
                                )

                                # Store successful refined response in the main vector DB
                                try:
                                    self.vector_store.store_generated_knowledge(
                                        query, refined_response, "vector_db_refined"
                                    )
                                except Exception as e:
                                    logger.warning(f"Back-store failed: {str(e)}")

                                logger.info(
                                    "Successfully refined response with local model"
                                )
                                return {
                                    "response_text": formatted_response,
                                    "source": "vector_db_refined",
                                    "confidence": confidence,
                                    "vector_results": vector_results,
                                }
                    except Exception as e:
                        logger.warning(f"Local model refinement error: {str(e)}")

                    # Refinement failed → use vector content directly
                    logger.info("Using vector content directly")
                    vector_direct = self._generate_response_from_vector(
                        query, vector_results, image_analysis, image_type, lang
                    )

                    if vector_direct and not vector_direct.startswith("__"):
                        return {
                            "response_text": vector_direct,
                            "source": "vector_db_direct",
                            "confidence": confidence,
                            "vector_results": vector_results,
                        }
            else:
                logger.info("No relevant results found in vector DB after filtering")

        # ── Step 2: Local model standalone ──
        logger.info("Step 2: Trying local model for direct response...")

        if lang == "de":
            local_prompt = f"{conversation_context}FRAGE: {query}\nANTWORT:"
        else:
            local_prompt = f"{conversation_context}QUESTION: {query}\nANSWER:"

        try:
            logger.info(f"Sending query to local model: {query[:50]}...")
            local_response = await self.local_model.generate_response(
                query=local_prompt, image_analysis=image_analysis, image_type=image_type
            )

            if local_response and local_response.get("success"):
                logger.info("Got successful response from local model")

                local_response_text = local_response["response"].strip()
                local_response_text = self._clean_response(local_response_text)

                apology_phrases = [
                    "apologize",
                    "sorry",
                    "can't answer",
                    "cannot answer",
                    "don't know",
                    "no information",
                    "not able to",
                ]
                is_apology = any(
                    phrase in local_response_text.lower() for phrase in apology_phrases
                )

                local_confidence = local_response.get("confidence", 0.7)

                if (
                    local_response_text
                    and len(local_response_text.split()) >= 5
                    and not is_apology
                    and local_confidence >= 0.65
                    and self._is_actionable_answer(local_response_text, query)
                ):
                    formatted_response = self._format_final_response(
                        local_response_text, query, lang, local_confidence
                    )

                    # Store successful local model response in the main vector DB
                    try:
                        self.vector_store.store_generated_knowledge(
                            query, local_response_text, "local_model"
                        )
                    except Exception as e:
                        logger.warning(f"Back-store failed: {str(e)}")

                    logger.info(
                        f"Local model response successful (confidence={local_confidence:.2f}, {len(local_response_text)} chars)"
                    )
                    return {
                        "response_text": formatted_response,
                        "source": "local_model",
                        "confidence": local_confidence,
                        "vector_results": vector_results if vector_results else None,
                    }
                else:
                    logger.warning(
                        f"Local model response rejected (confidence={local_confidence:.2f}, apology={is_apology}): {local_response_text[:100]}"
                    )
            else:
                logger.warning("Local model returned success=False")

        except Exception as e:
            logger.error(f"Local model error: {str(e)}", exc_info=True)

        # ── Step 3: ChatGPT API ──
        logger.info("Step 3: Trying ChatGPT API...")

        if lang == "de":
            gpt_prompt = f"""Du bist ein medizinischer Assistent. Beantworte die folgende Frage in vollständigen Sätzen:
{conversation_context}
    FRAGE: {query}

    Wichtige Regeln:
    1. Verwende vollständige Sätze
    2. Maximal {MAX_OUTPUT_LENGTH} Zeichen
    3. Sei hilfreich und informativ
    4. Berücksichtige den bisherigen Gesprächsverlauf

    ANTWORT:"""
        else:
            gpt_prompt = f"""You are a medical assistant. Answer the following question in complete sentences:
{conversation_context}
    QUESTION: {query}

    Important rules:
    1. Use complete sentences
    2. Maximum {MAX_OUTPUT_LENGTH} characters
    3. Be helpful and informative
    4. Consider the conversation history when answering

    ANSWER:"""

        try:
            chatgpt_result = await self.chatgpt.generate_medical_response(
                query=gpt_prompt, image_analysis=image_analysis, image_type=image_type
            )

            if chatgpt_result and chatgpt_result.get("success"):
                chatgpt_text = chatgpt_result["response"].strip()

                apology_phrases = [
                    "apologize",
                    "unable",
                    "sorry",
                    "can't",
                    "cannot",
                    "i'm sorry",
                    "don't know",
                    "no information",
                ]
                if not any(
                    phrase in chatgpt_text.lower() for phrase in apology_phrases
                ):
                    chatgpt_text = self._clean_response(chatgpt_text)

                    if (
                        chatgpt_text
                        and len(chatgpt_text.split()) >= 3
                        and self._is_actionable_answer(chatgpt_text, query)
                    ):
                        gpt_confidence = chatgpt_result.get("confidence", 0.85)
                        formatted_response = self._format_final_response(
                            chatgpt_text, query, lang, gpt_confidence
                        )

                        # Store successful ChatGPT response in the main vector DB
                        try:
                            self.vector_store.store_generated_knowledge(
                                query, chatgpt_text, "chatgpt_api"
                            )
                        except Exception as e:
                            logger.warning(f"Back-store failed: {str(e)}")

                        logger.info("ChatGPT API response successful")
                        return {
                            "response_text": formatted_response,
                            "source": "chatgpt_api",
                            "confidence": gpt_confidence,
                            "vector_results": (
                                vector_results if vector_results else None
                            ),
                        }
        except Exception as e:
            logger.error(f"ChatGPT API failed: {str(e)}")

        # ── Step 4: Local model simplified fallback ──
        logger.info("All methods failed, trying local model with simplified prompt")

        if lang == "de":
            simple_prompt = f"Was ist {query}? Bitte antworte kurz in 2-3 Sätzen."
        else:
            simple_prompt = f"What is {query}? Please answer briefly in 2-3 sentences."

        try:
            final_local_response = await self.local_model.generate_response(
                query=simple_prompt,
                image_analysis=None,
                image_type=None,
            )

            if final_local_response and final_local_response.get("success"):
                response_text = final_local_response["response"].strip()
                if (
                    response_text
                    and len(response_text.split()) >= 3
                    and self._is_actionable_answer(response_text, query)
                ):
                    formatted_response = self._format_final_response(
                        response_text, query, lang, 0.5
                    )

                    # Store fallback local-model knowledge in the main vector DB
                    # so repeated questions can be answered from Step 1.
                    try:
                        self.vector_store.store_generated_knowledge(
                            query, response_text, "local_model_fallback"
                        )
                    except Exception as e:
                        logger.warning(f"Back-store failed: {str(e)}")

                    logger.info("Final fallback local model successful")
                    return {
                        "response_text": formatted_response,
                        "source": "local_model_fallback",
                        "confidence": 0.5,
                        "vector_results": vector_results if vector_results else None,
                    }
        except Exception as e:
            logger.error(f"Final local model attempt failed: {str(e)}")

        # ── Step 5: Ultimate safe fallback ──
        if lang == "de":
            fallback_text = "Es tut mir leid, aber ich habe keine Informationen zu dieser Frage in meiner Datenbank. Bitte versuchen Sie, Ihre Frage anders zu formulieren oder konsultieren Sie einen Arzt für spezifische medizinische Fragen."
        else:
            fallback_text = "I'm sorry, but I don't have information about this question in my database. Please try rephrasing your question or consult a healthcare professional for specific medical inquiries."

        formatted_response = self._format_final_response(
            fallback_text, query, lang, 0.1
        )

        return {
            "response_text": formatted_response,
            "source": "fallback",
            "confidence": 0.1,
            "vector_results": vector_results if vector_results else None,
        }

    async def process_message(
        self,
        user_id: int,
        message_type: str,
        content: str,
        session_id: Optional[uuid.UUID] = None,
        image_type: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point for processing a chat message (text, audio, image, pdf).
        Routes to appropriate handler and returns bot response and metadata.
        """
        logger.info(
            f"Processing message: type={message_type}, user_id={user_id}, session_id={session_id}, has_query={bool(query)}"
        )

        # Get or create session for today if not provided
        if not session_id:
            session = await self._get_or_create_daily_session(
                user_id=user_id, session_id=None
            )
            session_id = cast(uuid.UUID, session.id)

        assert session_id is not None

        bot_response = None
        response_source = None
        image_analysis = None
        audio_transcript = None
        audio_url = None
        image_url = None
        pdf_text = None

        if message_type == "text":
            # Text message: get bot response
            bot_response = await self._get_response_with_hierarchy(
                content, session_id=session_id
            )
            response_source = bot_response.get("source", "unknown")

        elif message_type == "audio":
            # Audio message: decode base64, transcribe, and get bot response
            import base64

            if "," in content:
                base64_audio = content.split(",", 1)[1]
            else:
                base64_audio = content
            audio_bytes = base64.b64decode(base64_audio)

            # Save audio file first (before transcription)
            audio_url = await self._save_audio_to_storage(audio_bytes)

            # Then transcribe
            try:
                audio_transcript = self.audio_service.convert_audio_to_text(audio_bytes)
                bot_response = await self._get_response_with_hierarchy(
                    audio_transcript, session_id=session_id
                )
                response_source = bot_response.get("source", "unknown")
            except Exception as e:
                logger.error(f"Audio transcription failed: {str(e)}")
                # Use fallback text for response
                audio_transcript = (
                    "[Could not transcribe audio. Please try again or use text.]"
                )
                bot_response = await self._get_response_with_hierarchy(
                    "[User sent an audio message that could not be transcribed]",
                    session_id=session_id,
                )
                response_source = "error"

        elif message_type == "image":
            # Image message: save, analyze, and get bot response
            image_url = await self._save_image_to_storage(content)

            resolved_image_type = self._resolve_image_type(content, image_type, query)
            logger.info(
                f"Resolved image_type from requested={image_type} to resolved={resolved_image_type}"
            )

            # Perform medical image analysis
            image_analysis = self.image_service.process_base64_image(
                content, analyze_medical=True, image_type=resolved_image_type
            )

            # Build a direct response from the analysis data
            bot_response = await self._process_image_response(
                image_analysis, resolved_image_type, query
            )
            response_source = bot_response.get("source", "image")

        elif message_type == "pdf":
            # PDF message: save, extract text, and get bot response
            await self._save_pdf_to_storage(content)

            # Extract text from the PDF
            pdf_text = self._extract_text_from_pdf_base64(content)

            if not pdf_text or pdf_text.strip() == "":
                pdf_text = "[Could not extract text from the uploaded PDF]"

            # Build a prompt that combines PDF content with user query
            combined_prompt = self._build_pdf_query_prompt(pdf_text, query)

            bot_response = await self._get_response_with_hierarchy(
                combined_prompt, session_id=session_id
            )
            response_source = bot_response.get("source", "unknown")

        else:
            logger.warning(f"Unsupported message type: {message_type}")
            return {"error": f"Unsupported message type: {message_type}"}

        # Save user message to DB
        user_message_content = ""
        if message_type == "audio":
            user_message_content = (
                audio_transcript if audio_transcript else "[Audio message]"
            )
        elif message_type == "image":
            user_message_content = query if query else "[Image message]"
        elif message_type == "pdf":
            user_message_content = query if query else "[PDF document uploaded]"
        else:
            user_message_content = content

        await self._save_message(
            session_id=session_id,
            user_id=user_id,
            content=user_message_content,
            message_type=message_type,
            is_user=True,
            audio_url=audio_url,
            image_url=image_url,
        )

        # Format bot response before saving
        formatted_response = bot_response.get("response_text", "")

        # Truncate response if too long for database
        if len(formatted_response) > 5000:
            formatted_response = formatted_response[:4997] + "..."

        # Save the PROPERLY formatted bot response to DB
        await self._save_message(
            session_id=session_id,
            user_id=user_id,
            content=formatted_response,
            message_type="text",
            is_user=False,
            response_source=response_source,
        )

        # Update the bot_response with the formatted version
        bot_response["response_text"] = formatted_response

        logger.info(f"Bot response: {bot_response}")
        return {
            "status": "success",
            "bot_response": bot_response,
            "audio_transcript": audio_transcript if message_type == "audio" else None,
            "image_analysis": image_analysis,
            "session_id": str(session_id),
            "audio_url": audio_url,
            "image_url": image_url,
        }

    # ========== SESSION MANAGEMENT ==========

    async def _get_or_create_daily_session(
        self, user_id: int, session_id: Optional[uuid.UUID] = None
    ) -> ChatSession:
        """Get existing session or create new one (ONE PER DAY per user)"""
        today = date.today()

        async with self._create_async_session() as session:
            try:
                if session_id:
                    result = await session.execute(
                        select(ChatSession).where(
                            ChatSession.id == session_id, ChatSession.user_id == user_id
                        )
                    )
                    chat_session = result.scalar_one_or_none()
                    if chat_session:
                        logger.info(f"Retrieved existing session: {session_id}")
                        return chat_session

                # Try to get today's session
                result = await session.execute(
                    select(ChatSession).where(
                        and_(
                            ChatSession.user_id == user_id,
                            ChatSession.session_date == today,
                        )
                    )
                )
                existing_session = result.scalar_one_or_none()

                if existing_session:
                    logger.info(
                        f"Found existing session for today: {existing_session.id}"
                    )
                    return existing_session

                # Create new session for today
                chat_session = ChatSession(
                    user_id=user_id,
                    title=f"Chat Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    session_date=today,
                    message_count=0,
                )

                session.add(chat_session)
                await session.commit()
                await session.refresh(chat_session)

                logger.info(f"Created new chat session for today: {chat_session.id}")
                return chat_session

            except IntegrityError:
                await session.rollback()
                logger.info(
                    "Session already exists (concurrent creation), fetching existing session"
                )
                # Another request created the session concurrently — fetch it
                result = await session.execute(
                    select(ChatSession).where(
                        and_(
                            ChatSession.user_id == user_id,
                            ChatSession.session_date == today,
                        )
                    )
                )
                existing_session = result.scalar_one_or_none()
                if existing_session:
                    return existing_session
                raise
            except Exception as e:
                logger.error(f"Error getting/creating session: {str(e)}")
                raise

    async def _save_message(
        self,
        session_id: uuid.UUID,
        user_id: int,
        content: str,
        message_type: str,
        is_user: bool,
        audio_url: Optional[str] = None,
        image_url: Optional[str] = None,
        response_source: Optional[str] = None,
    ) -> ChatMessage:
        """Save message to database"""
        async with self._create_async_session() as session:
            try:
                message = ChatMessage(
                    chat_session_id=session_id,
                    user_id=user_id,
                    message_type=message_type,
                    content=content,
                    is_user=is_user,
                    audio_url=audio_url,
                    image_url=image_url,
                    response_source=response_source,
                )
                session.add(message)
                await session.commit()
                await session.refresh(message)

                logger.debug(
                    f"Message saved: {message.id}, type: {message_type}, user: {is_user}"
                )
                return message

            except Exception as e:
                logger.error(f"Error saving message: {str(e)}")
                raise

    async def _update_session_message_count(self, session_id: uuid.UUID):
        """Update message count in session"""
        async with self._create_async_session() as session:
            try:
                # Get current count
                result = await session.execute(
                    select(func.count(ChatMessage.id)).where(
                        ChatMessage.chat_session_id == session_id
                    )
                )
                count = result.scalar() or 0

                # Update session
                await session.execute(
                    update(ChatSession)
                    .where(ChatSession.id == session_id)
                    .values(message_count=count, updated_at=datetime.utcnow())
                )
                await session.commit()

            except Exception as e:
                logger.error(f"Error updating session count: {str(e)}")
                raise

    # ========== FILE STORAGE ==========

    async def _save_audio_to_storage(self, audio_bytes: bytes) -> str:
        """Save audio file and return URL"""
        try:
            import uuid
            import os

            filename = f"audio_{uuid.uuid4()}.mp3"
            audio_dir = "uploads/audio"
            os.makedirs(audio_dir, exist_ok=True)
            filepath = os.path.join(audio_dir, filename)

            with open(filepath, "wb") as f:
                f.write(audio_bytes)

            return f"/uploads/audio/{filename}"

        except Exception as e:
            logger.error(f"Error saving audio: {str(e)}")
            return ""

    async def _save_image_to_storage(self, base64_image: str) -> str:
        """Save image file and return URL"""
        try:
            import base64
            import uuid
            import os

            # Decode base64
            if "," in base64_image:
                base64_image = base64_image.split(",", 1)[1]

            image_bytes = base64.b64decode(base64_image)

            filename = f"image_{uuid.uuid4()}.jpg"
            image_dir = "uploads/images"
            os.makedirs(image_dir, exist_ok=True)
            filepath = os.path.join(image_dir, filename)

            with open(filepath, "wb") as f:
                f.write(image_bytes)

            return f"/uploads/images/{filename}"

        except Exception as e:
            logger.error(f"Error saving image: {str(e)}")
            return ""

    async def _detect_image_type(self, image_content: str) -> str:
        """Auto-detect if image is skin or scalp"""
        try:
            analysis = self.image_service.analyze_image_features(image_content)
            if analysis.get("contains_hair", False):
                return "scalp"
            else:
                return "skin"
        except Exception:
            return "skin"

    async def _save_pdf_to_storage(self, base64_pdf: str) -> str:
        """Save PDF file and return URL"""
        try:
            import base64 as b64

            if "," in base64_pdf:
                base64_pdf = base64_pdf.split(",", 1)[1]

            pdf_bytes = b64.b64decode(base64_pdf)

            filename = f"pdf_{uuid.uuid4()}.pdf"
            pdf_dir = "uploads/pdfs"
            os.makedirs(pdf_dir, exist_ok=True)
            filepath = os.path.join(pdf_dir, filename)

            with open(filepath, "wb") as f:
                f.write(pdf_bytes)

            logger.info(f"PDF saved to {filepath}")
            return f"/uploads/pdfs/{filename}"

        except Exception as e:
            logger.error(f"Error saving PDF: {str(e)}")
            return ""

    def _extract_text_from_pdf_base64(self, base64_pdf: str) -> str:
        """Extract text content from a base64-encoded PDF"""
        try:
            import base64 as b64
            from pypdf import PdfReader
            import io

            if "," in base64_pdf:
                base64_pdf = base64_pdf.split(",", 1)[1]

            pdf_bytes = b64.b64decode(base64_pdf)
            reader = PdfReader(io.BytesIO(pdf_bytes))

            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text.strip())

            full_text = "\n".join(text_parts)

            # Limit extracted text to avoid overwhelming the AI model
            max_chars = 3000
            if len(full_text) > max_chars:
                full_text = full_text[:max_chars] + "..."

            logger.info(
                f"Extracted {len(full_text)} characters from PDF ({len(reader.pages)} pages)"
            )
            return full_text

        except Exception as e:
            logger.error(f"Error extracting text from PDF: {str(e)}")
            return ""

    async def _process_image_response(
        self, image_analysis: Dict, image_type: str, user_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process image analysis results and generate a response.
        Builds a direct response from the analysis, then optionally enhances with LLM.
        """
        lang = self._detect_language(user_query) if user_query else "de"

        # Build a direct, informative response from the analysis data
        direct_response = self._build_direct_image_response(
            image_analysis, image_type, user_query, lang
        )

        # Try to enhance with LLM using a focused prompt
        try:
            analysis_text = self._serialize_image_analysis(image_analysis, image_type)
            if user_query:
                if lang == "de":
                    llm_prompt = (
                        f"Ein Patient hat ein {image_type}-Bild hochgeladen und fragt: {user_query}\n\n"
                        f"Die Bildanalyse ergab folgende Ergebnisse:\n{analysis_text}\n\n"
                        f"Beantworte die Frage des Patienten basierend auf diesen Ergebnissen. "
                        f"Sei hilfreich und informativ. Maximal {MAX_OUTPUT_LENGTH} Zeichen."
                    )
                else:
                    llm_prompt = (
                        f"A patient uploaded a {image_type} image and asks: {user_query}\n\n"
                        f"Image analysis results:\n{analysis_text}\n\n"
                        f"Answer the patient's question based on these results. "
                        f"Be helpful and informative. Maximum {MAX_OUTPUT_LENGTH} characters."
                    )
            else:
                if lang == "de":
                    llm_prompt = (
                        f"Ein Patient hat ein {image_type}-Bild zur Analyse hochgeladen.\n\n"
                        f"Die Bildanalyse ergab folgende Ergebnisse:\n{analysis_text}\n\n"
                        f"Gib eine hilfreiche medizinische Einschätzung basierend auf diesen Ergebnissen. "
                        f"Maximal {MAX_OUTPUT_LENGTH} Zeichen."
                    )
                else:
                    llm_prompt = (
                        f"A patient uploaded a {image_type} image for analysis.\n\n"
                        f"Image analysis results:\n{analysis_text}\n\n"
                        f"Provide a helpful medical assessment based on these results. "
                        f"Maximum {MAX_OUTPUT_LENGTH} characters."
                    )

            local_response = await self.local_model.generate_response(
                query=llm_prompt, image_analysis=None, image_type=None
            )

            if local_response and local_response.get("success"):
                response_text = local_response["response"].strip()
                response_text = self._clean_response(response_text)

                # Verify the LLM response is actually useful (not echoing instructions)
                bad_phrases = [
                    "please provide",
                    "based on the image",
                    "bitte geben",
                    "no description",
                    "image analysis above",
                    "basierend auf diesen ergebnissen",
                ]
                is_bad = any(p in response_text.lower() for p in bad_phrases)

                if response_text and len(response_text.split()) >= 8 and not is_bad:
                    formatted = self._format_final_response(
                        response_text, user_query or "image analysis", lang, 0.75
                    )
                    return {
                        "response_text": formatted,
                        "source": "image",
                        "confidence": 0.75,
                        "image_analysis": image_analysis,
                    }

        except Exception as e:
            logger.warning(f"LLM enhancement for image failed: {str(e)}")

        # Use the direct response built from analysis data
        formatted = self._format_final_response(
            direct_response, user_query or "image analysis", lang, 0.7
        )
        return {
            "response_text": formatted,
            "source": "image",
            "confidence": 0.7,
            "image_analysis": image_analysis,
        }

    def _serialize_image_analysis(self, image_analysis: Dict, image_type: str) -> str:
        """Convert image analysis dict into readable text for LLM prompts"""
        parts = []
        conditions = image_analysis.get("detected_conditions", [])
        if conditions:
            for cond in conditions:
                if isinstance(cond, dict):
                    name = cond.get("condition", "Unknown")
                    conf = cond.get("confidence", 0)
                    desc = cond.get("description", "")
                    symptoms = cond.get("common_symptoms", [])
                    line = f"- {name} (confidence: {conf:.0%})"
                    if desc:
                        line += f": {desc}"
                    if symptoms:
                        line += f" | Symptoms: {', '.join(symptoms)}"
                    parts.append(line)

        severity = image_analysis.get("severity_estimate", "")
        if severity and severity != "none":
            parts.append(f"Severity: {severity}")

        recommendations = image_analysis.get("recommendations", [])
        if recommendations:
            parts.append("Recommendations: " + "; ".join(recommendations[:4]))

        return "\n".join(parts) if parts else "No specific findings detected."

    def _build_direct_image_response(
        self,
        image_analysis: Dict,
        image_type: str,
        user_query: Optional[str],
        lang: str,
    ) -> str:
        """Build a complete, informative response directly from image analysis data"""
        conditions = image_analysis.get("detected_conditions", [])
        severity = image_analysis.get("severity_estimate", "unknown")
        recommendations = image_analysis.get("recommendations", [])

        if lang == "de":
            if conditions:
                parts = [
                    f"Die Bildanalyse Ihres {image_type}-Bildes hat folgende mögliche Befunde ergeben:"
                ]
                for cond in conditions:
                    if isinstance(cond, dict):
                        name = cond.get("condition", "Unbekannt")
                        conf = cond.get("confidence", 0)
                        desc = cond.get("description", "")
                        line = f"- {name} (Wahrscheinlichkeit: {conf:.0%})"
                        if desc:
                            line += f": {desc}"
                        parts.append(line)
                if severity and severity != "none":
                    severity_map = {
                        "high": "hoch",
                        "moderate": "mittel",
                        "low": "gering",
                    }
                    parts.append(
                        f"\nGeschätzter Schweregrad: {severity_map.get(severity, severity)}"
                    )
                if recommendations:
                    parts.append("\nEmpfehlungen:")
                    for rec in recommendations[:5]:
                        parts.append(f"- {rec}")
            else:
                parts = [
                    f"Die Bildanalyse Ihres {image_type}-Bildes hat keine spezifischen Befunde ergeben.",
                    "Das Bild erscheint unauffällig, aber bitte konsultieren Sie einen Arzt für eine genaue Diagnose.",
                ]
        else:
            if conditions:
                parts = [
                    f"The analysis of your {image_type} image has identified the following possible findings:"
                ]
                for cond in conditions:
                    if isinstance(cond, dict):
                        name = cond.get("condition", "Unknown")
                        conf = cond.get("confidence", 0)
                        desc = cond.get("description", "")
                        line = f"- {name} (likelihood: {conf:.0%})"
                        if desc:
                            line += f": {desc}"
                        parts.append(line)
                if severity and severity != "none":
                    parts.append(f"\nEstimated severity: {severity}")
                if recommendations:
                    parts.append("\nRecommendations:")
                    for rec in recommendations[:5]:
                        parts.append(f"- {rec}")
            else:
                parts = [
                    f"The analysis of your {image_type} image did not detect any specific conditions.",
                    "The image appears normal, but please consult a doctor for an accurate diagnosis.",
                ]

        return "\n".join(parts)

    def _build_pdf_query_prompt(
        self, pdf_text: str, user_query: Optional[str] = None
    ) -> str:
        """Build a prompt combining extracted PDF text with user query"""
        parts = []

        if user_query:
            parts.append(f"Patient's question: {user_query}")

        parts.append(f"Content from the uploaded medical document:\n{pdf_text}")

        if user_query:
            parts.append(
                "\nPlease analyze the medical document above and answer the patient's question."
            )
        else:
            parts.append(
                "\nPlease provide a summary and analysis of this medical document."
            )

        return "\n".join(parts)

    # ========== CHAT HISTORY ==========

    async def get_chat_history(
        self,
        user_id: int,
        session_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 50,
        is_admin: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get chat history for user"""
        async with self._create_async_session() as session:
            try:
                logger.info(
                    f"🔍 Fetching chat history - Target User: {user_id}, Session: {session_id}, Admin: {is_admin}"
                )

                # ---------- SINGLE SESSION (by ID) ----------
                if session_id:
                    logger.info(f"📁 Fetching specific session: {session_id}")

                    # Build query - ALWAYS check session_id, but user_id filter only for non-admins
                    query = select(ChatSession).where(ChatSession.id == session_id)

                    # Only filter by user_id if NOT admin
                    if not is_admin:
                        query = query.where(ChatSession.user_id == user_id)
                        logger.info(f"Non-admin: filtering by user_id={user_id}")
                    else:
                        logger.info("Admin: bypassing user_id filter")

                    result = await session.execute(query)
                    chat_session = result.scalar_one_or_none()

                    if not chat_session:
                        if is_admin:
                            logger.warning(
                                f"❌ Session {session_id} not found in database"
                            )
                        else:
                            logger.warning(
                                f"❌ Session {session_id} not found for user {user_id}"
                            )
                        return []

                    # Get ALL messages for this session
                    messages_result = await session.execute(
                        select(ChatMessage)
                        .where(ChatMessage.chat_session_id == session_id)
                        .order_by(ChatMessage.timestamp.asc())
                    )
                    messages = messages_result.scalars().all()

                    logger.info(
                        f"Found {len(messages)} messages for session {session_id}"
                    )

                    # Format messages with all available fields
                    message_responses = []
                    for msg in messages:
                        timestamp = cast(Optional[datetime], msg.timestamp)
                        message_dict = {
                            "id": str(msg.id),
                            "chat_session_id": str(msg.chat_session_id),
                            "user_id": msg.user_id,
                            "message_type": msg.message_type,
                            "content": msg.content,
                            "is_user": msg.is_user,
                            "timestamp": (
                                timestamp.isoformat() if timestamp is not None else None
                            ),
                            "response_source": getattr(msg, "response_source", None),
                            "audio_url": getattr(msg, "audio_url", None),
                            "image_url": getattr(msg, "image_url", None),
                        }
                        message_responses.append(message_dict)

                    # Return single session in a list
                    return [
                        {
                            "id": str(chat_session.id),
                            "user_id": chat_session.user_id,
                            "title": chat_session.title or "Unbenanntes Gespräch",
                            "created_at": chat_session.created_at,
                            "updated_at": chat_session.updated_at,
                            "session_date": chat_session.session_date,
                            "message_count": len(message_responses),
                            "messages": message_responses,
                        }
                    ]

                # ---------- ALL SESSIONS (no session_id) ----------
                else:
                    logger.info(f"📚 Fetching all sessions for user: {user_id}")

                    # Get all sessions for the specified user
                    query = select(ChatSession).where(ChatSession.user_id == user_id)

                    result = await session.execute(
                        query.order_by(ChatSession.updated_at.desc())
                    )
                    sessions = result.scalars().all()

                    logger.info(f"📋 Found {len(sessions)} total sessions")

                    session_data_list = []
                    for session_obj in sessions:
                        # Get messages for this session (limit to last 5 for performance)
                        messages_result = await session.execute(
                            select(ChatMessage)
                            .where(ChatMessage.chat_session_id == session_obj.id)
                            .order_by(ChatMessage.timestamp.desc())
                            .limit(5)
                        )
                        messages = messages_result.scalars().all()
                        # Reverse to get chronological order
                        messages = list(reversed(messages))

                        # Format messages
                        message_responses = []
                        for msg in messages:
                            timestamp = cast(Optional[datetime], msg.timestamp)
                            message_responses.append(
                                {
                                    "id": str(msg.id),
                                    "chat_session_id": str(msg.chat_session_id),
                                    "user_id": msg.user_id,
                                    "message_type": msg.message_type,
                                    "content": msg.content,
                                    "is_user": msg.is_user,
                                    "timestamp": (
                                        timestamp.isoformat()
                                        if timestamp is not None
                                        else None
                                    ),
                                    "response_source": getattr(
                                        msg, "response_source", None
                                    ),
                                    "audio_url": getattr(msg, "audio_url", None),
                                    "image_url": getattr(msg, "image_url", None),
                                }
                            )

                        session_data_list.append(
                            {
                                "id": str(session_obj.id),
                                "user_id": session_obj.user_id,
                                "title": session_obj.title or "Unbenanntes Gespräch",
                                "created_at": session_obj.created_at,
                                "updated_at": session_obj.updated_at,
                                "session_date": session_obj.session_date,
                                "message_count": session_obj.message_count
                                or len(message_responses),
                                "messages": message_responses,
                            }
                        )

                    return session_data_list

            except Exception as e:
                logger.error(f"💥 Error getting chat history: {str(e)}", exc_info=True)
                raise

    async def get_chat_By_userId(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """Get chat history for user with optimized pagination"""
        async with self._create_async_session() as session:
            try:
                logger.info(
                    f"📊 Fetching chat history for user {user_id} (page {page}, size {page_size})"
                )

                # First, get total count of sessions
                count_result = await session.execute(
                    select(func.count(ChatSession.id)).where(
                        ChatSession.user_id == user_id
                    )
                )
                total_sessions = count_result.scalar() or 0

                # Get paginated sessions
                offset = (page - 1) * page_size
                result = await session.execute(
                    select(ChatSession)
                    .where(ChatSession.user_id == user_id)
                    .order_by(ChatSession.updated_at.desc())
                    .offset(offset)
                    .limit(page_size)
                )
                sessions = result.scalars().all()

                session_data_list = []
                for session_obj in sessions:
                    # Get messages for this session (limit to last 5 for preview)
                    messages_result = await session.execute(
                        select(ChatMessage)
                        .where(ChatMessage.chat_session_id == session_obj.id)
                        .order_by(ChatMessage.timestamp.desc())
                        .limit(5)
                    )
                    messages = messages_result.scalars().all()

                    # Reverse to get chronological order
                    messages = list(reversed(messages))

                    # Create message responses with all fields
                    message_responses = []
                    for msg in messages:
                        timestamp = cast(Optional[datetime], msg.timestamp)
                        message_responses.append(
                            {
                                "id": str(msg.id),
                                "chat_session_id": str(msg.chat_session_id),
                                "user_id": msg.user_id,
                                "message_type": msg.message_type,
                                "content": msg.content,
                                "is_user": msg.is_user,
                                "timestamp": (
                                    timestamp.isoformat()
                                    if timestamp is not None
                                    else None
                                ),
                                "response_source": getattr(
                                    msg, "response_source", None
                                ),
                                "audio_url": getattr(msg, "audio_url", None),
                                "image_url": getattr(msg, "image_url", None),
                            }
                        )

                    session_data_list.append(
                        {
                            "id": str(session_obj.id),
                            "user_id": session_obj.user_id,
                            "title": session_obj.title or "Unbenanntes Gespräch",
                            "created_at": session_obj.created_at,
                            "updated_at": session_obj.updated_at,
                            "session_date": session_obj.session_date,
                            "message_count": session_obj.message_count
                            or len(message_responses),
                            "messages": message_responses,
                        }
                    )

                logger.info(
                    f"✅ Returning {len(session_data_list)} sessions for user {user_id} (total: {total_sessions})"
                )

                return {
                    "sessions": session_data_list,
                    "total": total_sessions,
                    "page": page,
                    "page_size": page_size,
                }

            except Exception as e:
                logger.error(
                    f"💥 Error getting chat history for user {user_id}: {str(e)}",
                    exc_info=True,
                )
                raise
