# test_chat_endpoint.py - Test the actual FastAPI /chat endpoint
import requests
import json

BASE_URL = "http://localhost:8000"

def test_chat_endpoint():
    print("=" * 60)
    print("TESTING FASTAPI /CHAT ENDPOINT")
    print("=" * 60)
    
    # First, you might need to get a token (if authentication is required)
    # For testing, you might need to adjust based on your auth setup
    
    test_payloads = [
        {
            "message": "What is hypertension and how is it treated?",
            "user_id": 1
        },
        {
            "message": "Explain diabetes symptoms and diagnosis",
            "user_id": 1
        },
        {
            "message": "What are common heart disease risk factors?",
            "user_id": 1
        }
    ]
    
    for i, payload in enumerate(test_payloads, 1):
        print(f"\n{i}. Testing: '{payload['message']}'")
        
        try:
            response = requests.post(
                f"{BASE_URL}/chat",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"   ✓ Success!")
                
                if 'response' in result:
                    print(f"   Response: {result['response'][:150]}...")
                
                if 'sources' in result:
                    print(f"   Sources: {len(result.get('sources', []))} medical references")
                
                if 'context_chunks' in result:
                    print(f"   Context: {result['context_chunks']} medical chunks used")
            
            elif response.status_code == 401:
                print("   ⚠ Authentication required - add token to headers")
                # If you have a login endpoint, get token first
                print("   Try logging in first at /login endpoint")
            
            else:
                print(f"   Error: {response.text[:200]}")
                
        except requests.exceptions.ConnectionError:
            print("   ✗ Cannot connect to server. Is it running?")
            print("   Start with: uvicorn app.main:app --reload")
            break
        except Exception as e:
            print(f"   ✗ Error: {e}")

if __name__ == "__main__":
    test_chat_endpoint()