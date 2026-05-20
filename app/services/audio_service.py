# app/services/audio_service.py
from gtts import gTTS
import uuid
import os
from typing import Optional, Dict, Any
import base64
from pydub import AudioSegment
import io

from app.config.log.log_config import get_logger

logger = get_logger("audio_service")


class AudioService:
    def __init__(self):
        """Initialize AudioService with Whisper model."""
        self.whisper_available = False
        self.model = None
        self._init_whisper()

    def _init_whisper(self):
        """Initialize Whisper model if available."""
        try:
            import whisper

            logger.info("Loading Whisper model...")
            self.model = whisper.load_model("base")
            self.whisper_available = True
            logger.info("Whisper model loaded successfully")
        except ImportError:
            logger.warning(
                "Whisper not installed. Audio transcription will be limited."
            )
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {str(e)}")

    def convert_audio_to_text(
        self, audio_bytes: bytes, audio_format: str = "wav"
    ) -> str:
        """Transcribe audio to text using OpenAI Whisper."""
        try:
            import tempfile
            import whisper
            import os

            logger.info(
                f"Transcribing {len(audio_bytes)} bytes of {audio_format} audio..."
            )

            # Create a temporary file with proper permissions
            temp_dir = tempfile.gettempdir()
            temp_file = tempfile.NamedTemporaryFile(
                suffix=f".{audio_format}",
                delete=False,  # Don't auto-delete
                dir=temp_dir,
            )

            try:
                # Write audio bytes
                temp_file.write(audio_bytes)
                temp_file.flush()
                temp_file.close()

                logger.info(f"Saved audio to: {temp_file.name}")

                # Load whisper model if not already loaded
                if not self.model:
                    self.model = whisper.load_model("base")
                    self.whisper_available = True

                # Transcribe with medical context hint to improve accuracy
                result = self.model.transcribe(
                    temp_file.name,
                    initial_prompt="Medical question about health, disease, symptoms, treatment, cancer, diabetes, AIDS, medication, diagnosis.",
                )
                transcript = result.get("text", "").strip()

                logger.info(f"Whisper transcription: {transcript[:100]}...")
                return transcript if transcript else "[No speech detected]"

            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_file.name)
                except Exception as e:
                    logger.warning(f"Could not delete temp file {temp_file.name}: {e}")

        except Exception as e:
            logger.error(f"Whisper transcription failed: {str(e)}")
            # Try a simpler approach if whisper fails
            return self._fallback_transcription(audio_bytes, audio_format)

    def _fallback_transcription(self, audio_bytes: bytes, audio_format: str) -> str:
        """Fallback method if whisper fails"""
        try:
            # Try to use pydub to convert to wav first
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=audio_format)

            # Convert to 16kHz mono for better compatibility
            audio = audio.set_frame_rate(16000).set_channels(1)

            # Save to bytes
            wav_buffer = io.BytesIO()
            audio.export(wav_buffer, format="wav")
            wav_bytes = wav_buffer.getvalue()

            # Try whisper again with processed audio
            import tempfile
            import whisper

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(wav_bytes)
                tmp.flush()

                # Load model if not already loaded
                if not self.model:
                    self.model = whisper.load_model("base")
                    self.whisper_available = True

                result = self.model.transcribe(tmp.name)

                transcript = result.get("text", "").strip()
                return transcript if transcript else "[Audio could not be transcribed]"

        except Exception as e:
            logger.error(f"Fallback transcription also failed: {str(e)}")
            return "[Audio message - transcription failed]"

    def convert_to_mp3(self, audio_bytes: bytes, audio_format: str) -> bytes:
        """Convert wav or webm audio bytes to mp3 bytes using pydub."""
        try:
            logger.info(f"Converting {audio_format} to mp3 for storage/processing...")
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=audio_format)
            mp3_io = io.BytesIO()
            audio.export(mp3_io, format="mp3")
            logger.info("Conversion to mp3 successful.")
            return mp3_io.getvalue()
        except Exception as e:
            logger.error(f"Error converting {audio_format} to mp3: {str(e)}")

            # If conversion fails, try to transcribe the original audio
            try:
                logger.info("Falling back to direct transcription...")
                transcript = self.convert_audio_to_text(audio_bytes, audio_format)
                logger.info(f"Direct transcription result: {transcript}")
                # Return empty bytes since we can't convert to mp3
                return b""
            except Exception as transcribe_error:
                logger.error(f"Transcription also failed: {str(transcribe_error)}")
                return b""

    async def text_to_speech(self, text: str, language: str = "en") -> bytes:
        """Convert text to speech and return audio bytes."""
        try:
            logger.info(f"Converting text to speech: {text[:50]}...")
            tts = gTTS(text=text, lang=language)

            # Save to bytes buffer
            audio_buffer = io.BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)

            logger.info("Text-to-speech conversion successful")
            return audio_buffer.getvalue()

        except Exception as e:
            logger.error(f"Error in text-to-speech conversion: {str(e)}")
            raise

    async def text_to_speech_and_save(self, text: str, language: str = "en") -> str:
        """Convert text to speech and save to file, return file path."""
        try:
            audio_bytes = await self.text_to_speech(text, language)

            # Save to file
            filename = f"tts_{uuid.uuid4()}.mp3"
            audio_dir = "audiofiles"
            os.makedirs(audio_dir, exist_ok=True)
            filepath = os.path.join(audio_dir, filename)

            with open(filepath, "wb") as f:
                f.write(audio_bytes)

            logger.info(f"TTS audio saved to: {filepath}")
            return f"/audiofiles/{filename}"  # Return URL path

        except Exception as e:
            logger.error(f"Error saving TTS audio: {str(e)}")
            raise

    def process_base64_audio(self, base64_string: str) -> str:
        """Process base64 encoded audio string"""
        try:
            logger.info("Processing base64 encoded audio")

            # Remove data URL prefix if present
            if "," in base64_string:
                base64_string = base64_string.split(",")[1]

            # Decode base64
            audio_bytes: bytes = base64.b64decode(base64_string)

            # Try to detect format from data URL
            audio_format: str = "wav"  # default
            if "data:audio/" in base64_string:
                # Extract format from data URL
                if "data:audio/wav" in base64_string:
                    audio_format = "wav"
                elif (
                    "data:audio/mp3" in base64_string
                    or "data:audio/mpeg" in base64_string
                ):
                    audio_format = "mp3"
                elif "data:audio/ogg" in base64_string:
                    audio_format = "ogg"
                elif "data:audio/webm" in base64_string:
                    audio_format = "webm"

            return self.convert_audio_to_text(audio_bytes, audio_format)

        except Exception as e:
            logger.error(f"Error processing base64 audio: {str(e)}")
            return f"Could not process audio: {str(e)}"

    def validate_audio(
        self, audio_bytes: bytes, audio_format: str = "wav"
    ) -> Dict[str, Any]:
        """Validate audio file"""
        try:
            validation_result: Dict[str, Any] = {
                "is_valid": False,
                "format": audio_format,
                "size_bytes": len(audio_bytes),
                "message": "",
            }

            # Basic size validation
            if len(audio_bytes) == 0:
                validation_result["message"] = "Audio file is empty"
                return validation_result

            # Size limits (50MB for Whisper)
            max_size: int = 50 * 1024 * 1024  # 50MB
            if len(audio_bytes) > max_size:
                validation_result["message"] = (
                    f"Audio file too large. Max size: {max_size//(1024*1024)}MB"
                )
                return validation_result

            # Minimum size (1KB)
            min_size: int = 1024  # 1KB
            if len(audio_bytes) < min_size:
                validation_result["message"] = (
                    f"Audio file too small. Min size: {min_size} bytes"
                )
                return validation_result

            # Format validation
            supported_formats: list[str] = ["wav", "mp3", "m4a", "ogg", "flac", "webm"]
            if audio_format.lower() not in supported_formats:
                validation_result["message"] = (
                    f"Unsupported audio format. Supported: {supported_formats}"
                )
                return validation_result

            # Additional checks based on format
            if audio_format.lower() == "wav":
                # Check WAV header (optional, can be complex)
                if len(audio_bytes) > 44 and audio_bytes[:4] != b"RIFF":
                    validation_result["message"] = "Invalid WAV file format"
                    return validation_result

            validation_result["is_valid"] = True
            validation_result["message"] = "Audio file is valid"

            return validation_result

        except Exception as e:
            logger.error(f"Error validating audio: {str(e)}")
            return {
                "is_valid": False,
                "format": audio_format,
                "size_bytes": len(audio_bytes) if audio_bytes else 0,
                "message": f"Validation error: {str(e)}",
            }

    def _fallback_response(self, error: Optional[str] = None) -> str:
        """Fallback response when Whisper is not available or fails"""
        import random

        base_responses: list[str] = [
            "I received your audio message but speech recognition is not fully configured. "
            "Please ensure Whisper is installed or use text input.",
            "Your audio message has been received. The speech recognition service is "
            "currently unavailable. Please use text input instead.",
            "Audio input detected. For now, please use text input or ensure that "
            "OpenAI Whisper is properly installed on the server.",
        ]

        if error:
            return f"I encountered an error while processing your audio: {error}. Please try text input instead."

        return random.choice(base_responses)

    def get_audio_info(
        self, audio_bytes: bytes, audio_format: str = "wav"
    ) -> Dict[str, Any]:
        """Get information about the audio file"""
        try:
            return {
                "format": audio_format,
                "size_bytes": len(audio_bytes),
                "size_mb": round(len(audio_bytes) / (1024 * 1024), 2),
                "is_valid": self.validate_audio(audio_bytes, audio_format)["is_valid"],
                "whisper_available": self.whisper_available,
                "model_loaded": self.model is not None,
            }
        except Exception as e:
            logger.error(f"Error getting audio info: {str(e)}")
            return {"format": audio_format, "error": str(e)}

    def get_supported_formats(self) -> Dict[str, Any]:
        """Get information about supported audio formats"""
        return {
            "supported_formats": ["wav", "mp3", "m4a", "ogg", "flac", "webm"],
            "max_size_mb": 50,
            "recommended_format": "wav",
            "recommended_sample_rate": 16000,
            "recommended_channels": 1,
            "whisper_available": self.whisper_available,
        }


# Optional: Create a simplified version for testing without Whisper
class SimpleAudioService:
    """Simplified audio service for testing without Whisper"""

    def __init__(self) -> None:
        logger.info("SimpleAudioService initialized (no Whisper dependency)")
        self.whisper_available = False
        self.model = None

    def convert_audio_to_text(
        self, audio_bytes: bytes, audio_format: str = "wav"
    ) -> str:
        """Simple placeholder for audio conversion"""
        logger.info(f"Received audio: {len(audio_bytes)} bytes, format: {audio_format}")
        return "Audio processing is disabled in simple mode. Please use text input or install Whisper for speech recognition."

    def process_base64_audio(self, base64_string: str) -> str:
        """Process base64 audio in simple mode"""
        logger.info("Processing base64 audio in simple mode")
        return "Audio processing is disabled in simple mode. Please use text input."

    def validate_audio(
        self, audio_bytes: bytes, audio_format: str = "wav"
    ) -> Dict[str, Any]:
        """Simple validation"""
        return {
            "is_valid": False,
            "format": audio_format,
            "size_bytes": len(audio_bytes),
            "message": "SimpleAudioService - no real validation",
        }


# Factory function to create the appropriate audio service
def create_audio_service(
    use_whisper: bool = True, model_size: str = "base"
) -> AudioService:
    """
    Factory function to create audio service.

    Args:
        use_whisper: Whether to use Whisper (requires installation)
        model_size: Whisper model size if using Whisper

    Returns:
        AudioService instance
    """
    if use_whisper:
        try:
            logger.info(f"Creating AudioService with Whisper (model: {model_size})")
            # Test if whisper is available
            import whisper

            whisper.load_model("base")  # Test load

            service = AudioService()
            logger.info("AudioService with Whisper created successfully")
            return service
        except ImportError:
            logger.warning("Whisper not found, creating SimpleAudioService")
            service = SimpleAudioService()
            # Cast to AudioService type for compatibility
            service.__class__ = type(
                "AudioService", (AudioService, SimpleAudioService), {}
            )
            return service  # type: ignore
        except Exception as e:
            logger.error(f"Error creating AudioService: {str(e)}")
            logger.warning("Falling back to SimpleAudioService")
            service = SimpleAudioService()
            service.__class__ = type(
                "AudioService", (AudioService, SimpleAudioService), {}
            )
            return service  # type: ignore
    else:
        logger.info("Creating SimpleAudioService (Whisper disabled)")
        service = SimpleAudioService()
        service.__class__ = type("AudioService", (AudioService, SimpleAudioService), {})
        return service  # type: ignore
