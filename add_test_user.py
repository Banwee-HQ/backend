#!/usr/bin/env python3
"""
Simple script to add a test admin user to the database
"""
import asyncio
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from core.config import settings
from core.db import initialize_db
from models.accounts.user import User, UserRole, AccountStatus, VerificationStatus
from sqlalchemy import select
from core.utils.encryption import PasswordManager

# Load environment variables
load_dotenv('.env.dev')

async def add_test_user():
    """Add a test admin user to the database"""
    try:
        # Initialize database
        print("Initializing database...")
        await initialize_db(
            settings.SQLALCHEMY_DATABASE_URI,
            settings.ENVIRONMENT == 'local'
        )
        
        # Import all models
        import models
        
        from core.db import db_manager
        async with db_manager.session_factory() as db:
            # Check if user already exists
            result = await db.execute(select(User).where(User.email == 'admin@banwee.com'))
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                print(f"User admin@banwee.com already exists")
                print(f"  Role: {existing_user.role}")
                print(f"  Status: {existing_user.account_status}")
                print(f"  Verification: {existing_user.verification_status}")
                return
            
            # Create test admin user
            password_manager = PasswordManager()
            hashed_password = password_manager.hash_password('Admin123!')
            
            from models.accounts.user import uuid7
            new_user = User(
                id=uuid7(),
                email='admin@banwee.com',
                firstname='Admin',
                lastname='User',
                hashed_password=hashed_password,
                role=UserRole.ADMIN,
                account_status=AccountStatus.ACTIVE,
                verification_status=VerificationStatus.VERIFIED
            )
            
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            
            print(f"✅ Test admin user created successfully!")
            print(f"  Email: admin@banwee.com")
            print(f"  Password: Admin123!")
            print(f"  Role: {new_user.role}")
            print(f"  Status: {new_user.account_status}")
            print(f"  Verification: {new_user.verification_status}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(add_test_user())
