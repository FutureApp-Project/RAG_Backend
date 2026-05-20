# testing/test_auth_endpoint.py
import asyncio
import httpx
import json

async def test_auth_endpoint():
    print("Testing auth endpoint...")
    
    async with httpx.AsyncClient() as client:
        # Test 1: Valid login
        print("\n1. Testing valid login...")
        try:
            response = await client.post(
                "http://127.0.0.1:8000/auth/login",
                json={"username": "Eckhard", "password": "Eckhard123"},
                timeout=10.0
            )
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Success! Token: {data.get('access_token', '')[:50]}...")
            else:
                print(f"   Response: {response.text}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Test 2: Wrong password
        print("\n2. Testing wrong password...")
        try:
            response = await client.post(
                "http://127.0.0.1:8000/auth/login",
                json={"username": "Eckhard", "password": "wrong"},
                timeout=10.0
            )
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text}")
        except Exception as e:
            print(f"   Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_auth_endpoint())