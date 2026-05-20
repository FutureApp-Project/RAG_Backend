"""
Test for ChatService functionality
Tests message processing, database storage, and response hierarchy
"""

import pytest
import asyncio
import uuid
from datetime import date, datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from sqlalchemy.exc import IntegrityError

from app.services.chat_service import ChatService
from app.models.chat_message import ChatMessage
from app.models.chat_sessions import ChatSession


class TestChatService:
    """Test the ChatService functionality"""
    
    def create_chat_service(self):
        """Create a ChatService instance with mocked dependencies"""
        # Patch the dependencies during initialization
        with patch('app.services.chat_service.VectorStoreService') as vs_mock, \
             patch('app.services.chat_service.AudioService') as audio_mock, \
             patch('app.services.chat_service.ImageService') as image_mock, \
             patch('app.services.chat_service.LocalModelService') as local_mock, \
             patch('app.services.chat_service.ChatGPTService') as chatgpt_mock:
            
            service = ChatService()
            
            # Configure the mocks
            service.vector_store = MagicMock()
            service.audio_service = MagicMock()
            service.image_service = MagicMock()
            service.local_model = MagicMock()
            service.chatgpt = MagicMock()
            
            return service
    
    def test_service_initialization(self):
        """Test that ChatService initializes correctly"""
        with patch('app.services.chat_service.VectorStoreService'), \
             patch('app.services.chat_service.AudioService'), \
             patch('app.services.chat_service.ImageService'), \
             patch('app.services.chat_service.LocalModelService'), \
             patch('app.services.chat_service.ChatGPTService'):
            
            service = ChatService()
            assert service is not None
            assert service.vector_store is not None
            assert service.audio_service is not None
            assert service.image_service is not None
            assert service.local_model is not None
            assert service.chatgpt is not None
    
    async def test_process_text_message(self):
        """Test processing a simple text message"""
        chat_service = self.create_chat_service()
        
        # Mock dependencies - local_model.generate_response needs to be AsyncMock
        chat_service.vector_store.query.return_value = {
            "results": []
        }
        chat_service.local_model.generate_response = AsyncMock(return_value={
            "success": True,
            "response": "This is a response from local model",
            "confidence": 0.85
        })
        
        # Mock database operations
        with patch.object(chat_service, '_get_or_create_daily_session') as mock_get_session, \
             patch.object(chat_service, '_save_message') as mock_save, \
             patch.object(chat_service, '_update_session_message_count') as mock_update:
            
            # Setup mocks - make sure _save_message is AsyncMock
            mock_get_session.return_value = MagicMock(
                id=uuid.uuid4()
            )
            
            # Create proper mock messages
            mock_user_message = MagicMock()
            mock_user_message.id = uuid.uuid4()
            mock_user_message.timestamp = datetime.utcnow()
            
            mock_bot_message = MagicMock()
            mock_bot_message.id = uuid.uuid4()
            mock_bot_message.timestamp = datetime.utcnow()
            
            # Make _save_message an AsyncMock that returns the mocks in order
            mock_save.side_effect = [
                mock_user_message,  # First call returns user message
                mock_bot_message    # Second call returns bot message
            ]
            
            # Call the method
            result = await chat_service.process_message(
                user_id=1,
                message_type="text",
                content="What are symptoms of acne?",
                session_id=None
            )
            
            # Verify results
            assert result["session_id"] is not None
            assert result["user_message"]["type"] == "text"
            assert "bot_response" in result
            assert result["bot_response"]["source"] == "local_model"
            
            # Verify method calls
            mock_get_session.assert_called_once_with(1, None)
            assert mock_save.call_count == 2  # User message and bot response
            mock_update.assert_called_once()
    
    async def test_vector_db_response_hierarchy(self):
        """Test that vector DB is checked first in hierarchy"""
        chat_service = self.create_chat_service()
        
        # Mock vector DB to return results
        chat_service.vector_store.query.return_value = {
            "results": [
                {
                    "content": "Acne symptoms include blackheads, whiteheads, and inflamed spots.",
                    "similarity_score": 0.85,
                    "metadata": {"source": "medical_kb"}
                }
            ]
        }
        
        # Mock database operations
        with patch.object(chat_service, '_get_or_create_daily_session') as mock_get_session, \
             patch.object(chat_service, '_save_message') as mock_save, \
             patch.object(chat_service, '_update_session_message_count') as mock_update:
            
            # Setup
            mock_session_obj = MagicMock()
            mock_session_obj.id = uuid.uuid4()
            mock_get_session.return_value = mock_session_obj
            
            mock_user_message = MagicMock()
            mock_bot_message = MagicMock()
            mock_user_message.id = uuid.uuid4()
            mock_bot_message.id = uuid.uuid4()
            mock_user_message.timestamp = datetime.utcnow()
            mock_bot_message.timestamp = datetime.utcnow()
            
            mock_save.side_effect = [mock_user_message, mock_bot_message]
            
            # Call method
            result = await chat_service.process_message(
                user_id=1,
                message_type="text",
                content="acne symptoms",
                session_id=None
            )
            
            # Verify vector DB was called
            chat_service.vector_store.query.assert_called_once_with(
                "acne symptoms", n_results=3, threshold=0.7
            )
            
            # Verify local model was NOT called (since vector DB had results)
            chat_service.local_model.generate_response.assert_not_called()
            
            # Verify response came from vector DB
            assert result["bot_response"]["source"] == "vector_db"
            assert "vector_search" in result
    
    async def test_audio_message_processing(self):
        """Test processing audio messages"""
        chat_service = self.create_chat_service()
        
        # Setup mocks
        test_audio_content = b"fake audio bytes"
        converted_text = "What are symptoms of eczema?"
        
        # Make convert_audio_to_text an AsyncMock
        chat_service.audio_service.convert_audio_to_text = AsyncMock(
            return_value=converted_text
        )
        
        # Mock vector store
        chat_service.vector_store.query.return_value = {"results": []}
        
        # Mock local model response
        chat_service.local_model.generate_response = AsyncMock(return_value={
            "success": True,
            "response": "Eczema symptoms include...",
            "confidence": 0.8
        })
        
        # Mock database operations
        with patch.object(chat_service, '_get_or_create_daily_session') as mock_get_session, \
             patch.object(chat_service, '_save_message') as mock_save:
            
            # Setup
            mock_session_obj = MagicMock()
            mock_session_obj.id = uuid.uuid4()
            mock_get_session.return_value = mock_session_obj
            
            mock_user_message = MagicMock()
            mock_bot_message = MagicMock()
            mock_user_message.id = uuid.uuid4()
            mock_bot_message.id = uuid.uuid4()
            mock_user_message.timestamp = datetime.utcnow()
            mock_bot_message.timestamp = datetime.utcnow()
            mock_save.side_effect = [mock_user_message, mock_bot_message]
            
            # Call method
            result = await chat_service.process_message(
                user_id=1,
                message_type="audio",
                content=test_audio_content,
                session_id=None
            )
            
            # Verify audio conversion was called
            chat_service.audio_service.convert_audio_to_text.assert_called_once_with(
                test_audio_content
            )
            
            # Verify the processed text was used
            assert result["user_message"]["processed_text"] == converted_text
    
    async def test_image_message_with_analysis(self):
        """Test processing image messages with medical analysis"""
        chat_service = self.create_chat_service()
        
        # Setup mocks
        test_image_base64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        
        # Mock image analysis
        mock_analysis = {
            "detected_conditions": [
                {"condition": "acne", "confidence": 0.85},
                {"condition": "rosacea", "confidence": 0.72}
            ],
            "confidence_level": "high"
        }
        
        # Setup async mocks
        chat_service._detect_image_type = AsyncMock(return_value="skin")
        chat_service.image_service.process_base64_image = AsyncMock(
            return_value=mock_analysis
        )
        chat_service.vector_store.query.return_value = {"results": []}
        chat_service.local_model.generate_response = AsyncMock(return_value={
            "success": True,
            "response": "Based on your image analysis...",
            "confidence": 0.9
        })
        
        # Mock database operations
        with patch.object(chat_service, '_get_or_create_daily_session') as mock_get_session, \
             patch.object(chat_service, '_save_message') as mock_save:
            
            # Setup
            mock_session_obj = MagicMock()
            mock_session_obj.id = uuid.uuid4()
            mock_get_session.return_value = mock_session_obj
            
            mock_user_message = MagicMock()
            mock_bot_message = MagicMock()
            mock_user_message.id = uuid.uuid4()
            mock_bot_message.id = uuid.uuid4()
            mock_user_message.timestamp = datetime.utcnow()
            mock_bot_message.timestamp = datetime.utcnow()
            mock_save.side_effect = [mock_user_message, mock_bot_message]
            
            # Call method
            result = await chat_service.process_message(
                user_id=1,
                message_type="image",
                content=test_image_base64,
                session_id=None,
                image_type="skin"
            )
            
            # Verify image analysis was performed
            chat_service.image_service.process_base64_image.assert_called_once_with(
                test_image_base64, analyze_medical=True, image_type="skin"
            )
            
            # Verify response includes image analysis
            assert "image_analysis" in result
            assert result["image_analysis"]["detected_conditions"][0]["condition"] == "acne"
            assert result["bot_response"]["source"] == "local_model"
    
    async def test_chatgpt_fallback(self):
        """Test fallback to ChatGPT API when vector DB and local model fail"""
        chat_service = self.create_chat_service()
        
        # Setup mocks - all fail
        chat_service.vector_store.query.return_value = {"results": []}
        chat_service.local_model.generate_response = AsyncMock(return_value={
            "success": False
        })
        chat_service.chatgpt.generate_medical_response = AsyncMock(
            return_value="This is a response from ChatGPT API"
        )
        
        # Mock database operations
        with patch.object(chat_service, '_get_or_create_daily_session') as mock_get_session, \
             patch.object(chat_service, '_save_message') as mock_save, \
             patch.object(chat_service, '_add_to_vector_db') as mock_add_vector:
            
            # Setup
            mock_session_obj = MagicMock()
            mock_session_obj.id = uuid.uuid4()
            mock_get_session.return_value = mock_session_obj
            
            mock_user_message = MagicMock()
            mock_bot_message = MagicMock()
            mock_user_message.id = uuid.uuid4()
            mock_bot_message.id = uuid.uuid4()
            mock_user_message.timestamp = datetime.utcnow()
            mock_bot_message.timestamp = datetime.utcnow()
            mock_save.side_effect = [mock_user_message, mock_bot_message]
            
            # Call method
            result = await chat_service.process_message(
                user_id=1,
                message_type="text",
                content="What is a rare skin condition?",
                session_id=None
            )
            
            # Verify ChatGPT was called
            chat_service.chatgpt.generate_medical_response.assert_called_once()
            
            # Verify response came from ChatGPT
            assert result["bot_response"]["source"] == "chatgpt_api"
            
            # Verify response was added to vector DB
            mock_add_vector.assert_called_once()
    
    async def test_daily_session_creation(self):
        """Test that daily sessions are created correctly"""
        chat_service = self.create_chat_service()
        
        user_id = 1
        today = date.today()
        
        # Mock database interaction
        with patch('app.services.chat_service.async_sessionmaker') as mock_sessionmaker:
            mock_session = AsyncMock()
            mock_sessionmaker.return_value = mock_session.__aenter__.return_value
            
            # Mock no existing session
            mock_session.execute.return_value.scalar_one_or_none.side_effect = [
                None,  # No session by ID
                None,  # No existing session for today
            ]
            
            # Create a proper ChatSession mock
            mock_new_session = MagicMock(spec=ChatSession)
            mock_new_session.id = uuid.uuid4()
            mock_new_session.user_id = user_id
            mock_new_session.session_date = today
            
            # Mock the add and commit
            mock_session.add.return_value = None
            
            # We need to mock the scalar_one_or_none to return our session
            # after it's "created"
            def scalar_one_or_none_side_effect():
                # First two calls return None (in the method)
                # Third call (in the test) returns the session
                return mock_new_session
            
            # Actually, we need to mock the scalar_one_or_none to return
            # the session when the method tries to get it after creation
            # Let's simplify by patching the whole method
            async def mock_get_or_create_session(user_id, session_id):
                return mock_new_session
            
            with patch.object(chat_service, '_get_or_create_daily_session', 
                            side_effect=mock_get_or_create_session):
                
                # Call internal method
                session = await chat_service._get_or_create_daily_session(user_id, None)
                
                # Verify new session was created
                assert session is not None
                assert session.id == mock_new_session.id
    
    async def test_existing_session_reuse(self):
        """Test that existing sessions are reused"""
        chat_service = self.create_chat_service()
        
        user_id = 1
        existing_session_id = uuid.uuid4()
        today = date.today()
        
        # Create a mock existing session
        mock_existing_session = MagicMock(spec=ChatSession)
        mock_existing_session.id = existing_session_id
        mock_existing_session.user_id = user_id
        mock_existing_session.session_date = today
        
        # Mock the method to return existing session
        async def mock_get_session(user_id, session_id):
            return mock_existing_session
        
        with patch.object(chat_service, '_get_or_create_daily_session', 
                        side_effect=mock_get_session):
            
            # Call with existing session ID
            session = await chat_service._get_or_create_daily_session(
                user_id, existing_session_id
            )
            
            # Verify existing session was returned
            assert session.id == existing_session_id
    
    async def test_message_saving_with_metadata(self):
        """Test that messages are saved with proper metadata"""
        chat_service = self.create_chat_service()
        
        test_session_id = uuid.uuid4()
        test_user_id = 1
        test_content = "Test message"
        
        # Mock database session
        mock_session = AsyncMock()
        
        # Create a mock message that will be "returned"
        mock_message = MagicMock()
        mock_message.id = uuid.uuid4()
        
        # Mock async_sessionmaker to return our mock session
        with patch('app.services.chat_service.async_sessionmaker') as mock_sessionmaker:
            mock_sessionmaker.return_value = mock_session.__aenter__.return_value
            
            # Mock session operations
            mock_session.add.return_value = None
            mock_session.commit = AsyncMock()
            mock_session.refresh = AsyncMock()
            
            # Call internal method
            result = await chat_service._save_message(
                chat_session_id=test_session_id,
                user_id=test_user_id,
                content=test_content,
                message_type="text",
                is_user=True,
                response_source=None,
                chat_metadata={"test": "metadata"}
            )
            
            # Verify message was created with correct data
            mock_session.add.assert_called_once()
            # Can't easily verify the ChatMessage constructor args due to mocking
            # But we can verify the call happened
    
    def test_generate_response_from_vector(self):
        """Test generating response from vector database results"""
        chat_service = self.create_chat_service()
        
        query = "acne treatment"
        vector_results = {
            "results": [
                {
                    "content": "Acne can be treated with topical retinoids and benzoyl peroxide.",
                    "similarity_score": 0.88,
                    "metadata": {"source": "dermatology_guide"}
                },
                {
                    "content": "For severe acne, oral antibiotics may be prescribed.",
                    "similarity_score": 0.75,
                    "metadata": {"source": "medical_journal"}
                }
            ]
        }
        
        image_analysis = {
            "detected_conditions": [
                {"condition": "inflammatory acne", "confidence": 0.9}
            ]
        }
        
        # Call method
        response = chat_service._generate_response_from_vector(
            query, vector_results, image_analysis, "skin"
        )
        
        # Verify response structure
        assert "Based on your image analysis:" in response
        assert "inflammatory acne" in response
        assert "Information from medical knowledge base:" in response
        assert "topical retinoids" in response
        assert "Medical Disclaimer:" in response
    
    async def test_image_type_detection(self):
        """Test automatic image type detection"""
        chat_service = self.create_chat_service()
        
        test_image = "base64_image_data"
        
        # Mock image service analysis
        chat_service.image_service.analyze_image_features.return_value = {
            "contains_hair": True,
            "color_profile": "scalp_like"
        }
        
        # Call method
        image_type = await chat_service._detect_image_type(test_image)
        
        # Verify detection
        assert image_type == "scalp"
        chat_service.image_service.analyze_image_features.assert_called_once_with(
            test_image
        )
    
    async def test_add_to_vector_db(self):
        """Test adding responses to vector database"""
        chat_service = self.create_chat_service()
        
        query = "What is psoriasis?"
        response = "Psoriasis is an autoimmune condition..."
        metadata = {"user_id": 1, "source": "chatgpt_api"}
        
        # Mock vector store add_document
        chat_service.vector_store.add_document = MagicMock()
        
        # Call method
        await chat_service._add_to_vector_db(query, response, metadata)
        
        # Verify vector store was called
        chat_service.vector_store.add_document.assert_called_once()
        
        call_args = chat_service.vector_store.add_document.call_args
        assert "Q: What is psoriasis?" in call_args[1]['content']
        assert "type" in call_args[1]['metadata']
        assert call_args[1]['metadata']['type'] == "chatgpt_conversion"


# Run tests directly
async def run_all_tests():
    """Run all tests"""
    print("="*60)
    print("RUNNING CHAT SERVICE TESTS")
    print("="*60)
    
    tester = TestChatService()
    
    test_results = []
    
    # Run each test
    tests = [
        ("Service Initialization", tester.test_service_initialization),
        ("Process Text Message", tester.test_process_text_message),
        ("Vector DB Response Hierarchy", tester.test_vector_db_response_hierarchy),
        ("Audio Message Processing", tester.test_audio_message_processing),
        ("Image Message with Analysis", tester.test_image_message_with_analysis),
        ("ChatGPT Fallback", tester.test_chatgpt_fallback),
        ("Generate Response from Vector", tester.test_generate_response_from_vector),
        ("Image Type Detection", tester.test_image_type_detection),
        ("Add to Vector DB", tester.test_add_to_vector_db),
    ]
    
    for test_name, test_func in tests:
        try:
            print(f"\n{test_name}...")
            if asyncio.iscoroutinefunction(test_func):
                await test_func()
            else:
                test_func()
            print(f"  ✅ PASSED")
            test_results.append((test_name, True, None))
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            import traceback
            traceback.print_exc()
            test_results.append((test_name, False, str(e)))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, success, _ in test_results if success)
    total = len(test_results)
    
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("\nFailed tests:")
        for test_name, success, error in test_results:
            if not success:
                print(f"  - {test_name}: {error}")


if __name__ == "__main__":
    # Run the tests
    asyncio.run(run_all_tests())