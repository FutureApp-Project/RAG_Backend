# test_embedding_workflow.py
import asyncio
import sys
import os
from pathlib import Path
# Add the app directory to the path so we can import your service
#sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))
# FIX: Get the project root directory
project_root = Path(__file__).parent.parent  # Go up two levels from testing/
sys.path.insert(0, str(project_root))
async def test_embedding_pipeline():
    """Test the complete embedding pipeline from your service."""
    print("=" * 60)
    print("Testing Complete Embedding Pipeline")
    print("=" * 60)
    
    try:
        print("Importing VectorStoreService...")
        # Import your service
        from app.services.vector_store_service import VectorStoreService
        print("✓ Successfully imported VectorStoreService")
        # Initialize your service
        print("Initializing VectorStoreService...")
        vector_service = VectorStoreService()
        print("✓ VectorStoreService initialized")
        
        # Test 1: Test creating a collection
        print("\n1. Testing collection creation...")
        collection = vector_service.create_collection("test_collection")
        print(f"✓ Collection created/accessed: {collection.name}")
        
        # Test 2: Test a simple query (this will fail if embeddings are broken)
        print("\n2. Testing query functionality...")
        test_query = "What is machine learning?"
        result = vector_service.query(test_query, n_results=2)
        
        if result.get("error"):
            print(f"✗ Query failed with error: {result['error']}")
            print("  This likely means the embedding model is not working.")
        else:
            print(f"✓ Query executed successfully")
            print(f"  Found {result['total_found']} results")
            if result['results']:
                for i, res in enumerate(result['results']):
                    print(f"  Result {i+1}: {res['content'][:100]}...")
        
        # Test 3: Check collection stats
        print("\n3. Checking collection stats...")
        stats = vector_service.get_collection_stats("medical_documents")
        if "error" in stats:
            print(f"  Collection stats error (may be normal if empty): {stats['error']}")
        else:
            print(f"  Total documents: {stats['total_documents']}")
            print(f"  Sources: {stats['sources']}")
        
        # Test 4: Test the embedding model directly
        print("\n4. Testing embedding model directly...")
        try:
            # This accesses the embedding model from your service
            test_text = "Testing direct embedding"
            # Note: You might need to adjust this based on your actual implementation
            if hasattr(vector_service, 'embedding_model'):
                embeddings = vector_service.embedding_model.embed_query(test_text)
                print(f"✓ Direct embedding successful")
                print(f"  Embedding dimensions: {len(embeddings)}")
                print(f"  Sample values: {embeddings[:3]}")
            else:
                print("✗ No embedding_model attribute found in VectorStoreService")
        except Exception as e:
            print(f"✗ Direct embedding failed: {e}")
        
        print("\n" + "=" * 60)
        print("Test completed")
        print("=" * 60)
        
    except ImportError as e:
        print(f"✗ Failed to import VectorStoreService: {e}")
        print("Make sure you're running from the correct directory")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")

if __name__ == "__main__":
    # Run the async test
    asyncio.run(test_embedding_pipeline())