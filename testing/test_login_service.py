# test_login_service.py
import asyncio
from app.services.login_service import login_service

async def test_login_service():
    print("Testing login service...")
    
    # Test Eckhard login
    print("\n1. Testing Eckhard login...")
    result = await login_service.login("Eckhard", "Eckhard123")
    print(f"   Result: {result}")
    
    # Test with wrong password
    print("\n2. Testing Eckhard with wrong password...")
    result = await login_service.login("Eckhard", "wrong")
    print(f"   Result: {result}")
    
    # Test bot login
    print("\n3. Testing bot login...")
    result = await login_service.login("bot", "botpassword")
    print(f"   Result: {result}")
    
    # Test non-existent user
    print("\n4. Testing non-existent user...")
    result = await login_service.login("nonexistent", "password")
    print(f"   Result: {result}")

if __name__ == "__main__":
    asyncio.run(test_login_service())