# test_embeddings_debug.py
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

def test_embedding_details():
    """Debug embedding issues"""
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text:latest")
    
    print("=" * 60)
    print("Debugging Embedding Issues")
    print("=" * 60)
    
    # Test different prompts
    test_prompts = [
        "Hello world",
        "Machine learning is fascinating",
        "The quick brown fox jumps over the lazy dog",
        "Embeddings are vector representations of text"
    ]
    
    for i, prompt in enumerate(test_prompts, 1):
        print(f"\nTest {i}: '{prompt}'")
        
        payload = {
            "model": ollama_model,
            "prompt": prompt
        }
        
        try:
            response = requests.post(
                f"{ollama_base_url}/api/embed",
                json=payload,
                timeout=30
            )
            
            print(f"  Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                embeddings = result.get("embedding", [])
                print(f"  Embedding length: {len(embeddings)}")
                
                if len(embeddings) > 0:
                    print(f"  First 3 values: {embeddings[:3]}")
                    print(f"  Last 3 values: {embeddings[-3:]}")
                    # Check for zeros
                    zero_count = sum(1 for x in embeddings if abs(x) < 0.0001)
                    print(f"  Near-zero values (<0.0001): {zero_count}/{len(embeddings)}")
                else:
                    print(f"  WARNING: Empty embedding array!")
                    print(f"  Full response: {json.dumps(result, indent=2)}")
            else:
                print(f"  Error: {response.text}")
                
        except Exception as e:
            print(f"  Exception: {e}")

def test_model_info():
    """Get detailed model information"""
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text:latest")
    
    print("\n" + "=" * 60)
    print("Model Information")
    print("=" * 60)
    
    try:
        # Get model info
        response = requests.post(
            f"{ollama_base_url}/api/show",
            json={"name": ollama_model},
            timeout=10
        )
        
        if response.status_code == 200:
            model_info = response.json()
            print(f"Model: {model_info.get('model')}")
            print(f"Parameters: {model_info.get('parameters', 'N/A')}")
            print(f"Template: {model_info.get('template', 'N/A')[:100]}...")
            print(f"License: {model_info.get('license', 'N/A')}")
            
            # Check if it's an embedding model
            details = model_info.get('details', {})
            print(f"Family: {details.get('family', 'Unknown')}")
            print(f"Parameter Size: {details.get('parameter_size', 'Unknown')}")
            print(f"Quantization Level: {details.get('quantization_level', 'Unknown')}")
            
        else:
            print(f"Failed to get model info: {response.text}")
            
    except Exception as e:
        print(f"Error getting model info: {e}")

def test_alternative_embedding_model():
    """Try alternative embedding models"""
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    print("\n" + "=" * 60)
    print("Testing Alternative Models")
    print("=" * 60)
    
    # Try different embedding models
    alternative_models = [
        "nomic-embed-text:latest",  # The one you have
        "all-minilm",  # Smaller alternative
        "mxbai-embed-large",  # Another good embedding model
    ]
    
    for model in alternative_models:
        print(f"\nTrying model: {model}")
        
        # First check if model exists
        try:
            response = requests.post(
                f"{ollama_base_url}/api/show",
                json={"name": model},
                timeout=10
            )
            
            if response.status_code != 200:
                print(f"  Model not available, pulling...")
                # Try to pull it
                pull_response = requests.post(
                    f"{ollama_base_url}/api/pull",
                    json={"name": model},
                    timeout=300
                )
                print(f"  Pull status: {pull_response.status_code}")
                continue
                
        except Exception as e:
            print(f"  Error checking model: {e}")
            continue
        
        # Test embedding
        payload = {
            "model": model,
            "prompt": "Test embedding"
        }
        
        try:
            response = requests.post(
                f"{ollama_base_url}/api/embed",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                embeddings = result.get("embedding", [])
                print(f"  ✓ Embedding length: {len(embeddings)}")
                if len(embeddings) > 0:
                    print(f"  First value: {embeddings[0]}")
            else:
                print(f"  ✗ Failed: {response.text[:100]}")
                
        except Exception as e:
            print(f"  ✗ Error: {e}")

if __name__ == "__main__":
    test_embedding_details()
    test_model_info()
    test_alternative_embedding_model()