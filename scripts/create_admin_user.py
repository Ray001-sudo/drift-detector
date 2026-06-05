import asyncio
import re
import sys
import getpass
from sqlalchemy import select
from common.database import async_session_maker
from common.models import User
from common.security import get_password_hash
from common.config import settings

def validate_username(username: str) -> bool:
    return bool(re.match(r"^\w{3,64}$", username))

def validate_password(password: str) -> bool:
    if len(password) < 16:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"[0-9]", password):
        return False
    if not re.search(r"[^A-Za-z0-9]", password):
        return False
    return True

async def main() -> None:
    print("=== Create Admin User ===")
    
    while True:
        username = input("Username (3-64 chars, alphanumeric/underscore): ").strip()
        if validate_username(username):
            break
        print("Invalid username format.")

    while True:
        password = getpass.getpass("Password (min 16 chars, upper, lower, digit, special): ")
        if validate_password(password):
            break
        print("Password does not meet complexity requirements.")
        
    while True:
        role = input("Role (viewer/admin) [admin]: ").strip().lower() or "admin"
        if role in ("viewer", "admin"):
            break
        print("Invalid role. Must be 'viewer' or 'admin'.")

    try:
        async with async_session_maker() as session:
            stmt = select(User).where(User.username == username)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                print(f"Error: User '{username}' already exists.")
                sys.exit(1)
            
            new_user = User(
                username=username,
                password_hash=get_password_hash(password),
                role=role
            )
            session.add(new_user)
            await session.commit()
            
            host = settings.DASHBOARD_HOST
            print(f"\nAdmin user '{username}' created successfully with role '{role}'.")
            print(f"You may now log in at https://{host}/auth/token")
    except Exception as e:
        print(f"Database connection error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
