# debug_login.py
import asyncio
from app.config.database.database import AsyncSessionLocal
from app.models.user import User
from app.models.role import Role
from app.config.helper.password_helper import password_helper
from app.config.security import security_config
from sqlalchemy import select

async def debug_login():
    print("Debugging login issue...")
    
    async with AsyncSessionLocal() as session:
        # Check Eckhard user
        print("\n1. Checking Eckhard user...")
        result = await session.execute(
            select(User, Role).join(Role, User.role_id == Role.id).where(User.username == "Eckhard")
        )
        row = result.first()
        
        if row:
            user, role = row
            print(f"   User found: {user.username}")
            print(f"   Firstname: {user.firstname}, Lastname: {user.lastname}")
            print(f"   Role: {role.role}")
            print(f"   Is active: {user.is_active}")
            print(f"   Password hash: {user.password[:30]}...")
            
            # Test password with security_config directly
            print("\n2. Testing password verification...")
            test_password = "Eckhard123"
            
            # Try direct verification
            try:
                direct_result = security_config.verify_password(test_password, user.password)
                print(f"   Direct verification result: {direct_result}")
            except Exception as e:
                print(f"   Direct verification error: {e}")
            
            # Try with password_helper
            async_result = await password_helper.verify_password(test_password, user.password)
            print(f"   Async verification result: {async_result}")
            
            # Try to re-hash and compare
            print("\n3. Testing re-hashing...")
            new_hash = await password_helper.get_password_hash(test_password)
            print(f"   New hash for '{test_password}': {new_hash[:30]}...")
            print(f"   Old hash: {user.password[:30]}...")
            
            # Are they the same?
            print(f"   Hashes match: {user.password == new_hash}")
            
            # Verify the new hash
            new_verify = await password_helper.verify_password(test_password, new_hash)
            print(f"   New hash verification: {new_verify}")
            
            # Try a wrong password
            wrong_result = await password_helper.verify_password("wrong", user.password)
            print(f"   Wrong password verification: {wrong_result}")
        else:
            print("   ERROR: Eckhard user not found!")
        
        # Check bot user
        print("\n4. Checking bot user...")
        result = await session.execute(
            select(User, Role).join(Role, User.role_id == Role.id).where(User.username == "bot")
        )
        row = result.first()
        
        if row:
            user, role = row
            print(f"   Bot user found: {user.username}")
            print(f"   Is active: {user.is_active}")
            
            # Test bot password
            bot_result = await password_helper.verify_password("botpassword", user.password)
            print(f"   Bot password verification: {bot_result}")

if __name__ == "__main__":
    asyncio.run(debug_login())