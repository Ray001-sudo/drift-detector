import asyncio
from sqlalchemy import select
from common.database import async_session_maker
from common.models import User
import bcrypt

async def main() -> None:
    username = "admin"
    password = "AdminPassword123!"
    role = "admin"

    try:
        async with async_session_maker() as session:
            stmt = select(User).where(User.username == username)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                print(f"User '{username}' already exists. Password might be different.")
                return
            
            # Bypass passlib bcrypt version bug
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
            
            new_user = User(
                username=username,
                password_hash=hashed,
                role=role
            )
            session.add(new_user)
            await session.commit()
            
            print(f"Admin user '{username}' created successfully with role '{role}'.")
            print(f"Password: {password}")
    except Exception as e:
        print(f"Database connection error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
