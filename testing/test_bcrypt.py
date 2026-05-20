# test_bcrypt.py
import bcrypt

print(f"bcrypt module location: {bcrypt.__file__}")
print(f"bcrypt attributes: {dir(bcrypt)}")

# Try to check version
try:
    if hasattr(bcrypt, '__about__'):
        print(f"bcrypt.__about__ exists: {bcrypt.__about__}")
        if hasattr(bcrypt.__about__, '__version__'):
            print(f"bcrypt version: {bcrypt.__about__.__version__}")
    elif hasattr(bcrypt, '__version__'):
        print(f"bcrypt.__version__ exists: {bcrypt.__version__}")
    else:
        print("No version attribute found in bcrypt module")
except Exception as e:
    print(f"Error checking bcrypt: {e}")

# Try to use bcrypt directly
try:
    password = b"testpassword"
    hashed = bcrypt.hashpw(password, bcrypt.gensalt())
    print(f"Hashed password: {hashed}")
    
    # Verify
    check = bcrypt.checkpw(password, hashed)
    print(f"Password verification: {check}")
except Exception as e:
    print(f"Error using bcrypt: {e}")