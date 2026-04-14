#!/usr/bin/env python3
"""
Script to add test users to the database
Creates admin and/or customer users for testing purposes
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

async def add_test_user(user_type: str = 'all'):
    """Add test users to the database

    Args:
        user_type: 'guest', 'admin', 'manager', 'support', 'customer', or 'all' (default)
    """
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
        password_manager = PasswordManager()

        async with db_manager.session_factory() as db:
            users_to_create = []

            # Guest user
            if user_type in ['guest', 'all']:
                result = await db.execute(select(User).where(User.email == 'guest@banwee.com'))
                existing_guest = result.scalar_one_or_none()

                if not existing_guest:
                    users_to_create.append({
                        'email': 'guest@banwee.com',
                        'password': 'Guest123!',
                        'firstname': 'Guest',
                        'lastname': 'User',
                        'role': UserRole.GUEST,
                        'phone': '+1234567890'
                    })
                else:
                    print(f"✓ Guest user already exists: guest@banwee.com")

            # Admin user
            if user_type in ['admin', 'all']:
                result = await db.execute(select(User).where(User.email == 'admin@banwee.com'))
                existing_admin = result.scalar_one_or_none()

                if not existing_admin:
                    users_to_create.append({
                        'email': 'admin@banwee.com',
                        'password': 'Admin123!',
                        'firstname': 'Admin',
                        'lastname': 'User',
                        'role': UserRole.ADMIN,
                        'phone': '+1234567890'
                    })
                else:
                    print(f"✓ Admin user already exists: admin@banwee.com")

            # Manager user
            if user_type in ['manager', 'all']:
                result = await db.execute(select(User).where(User.email == 'manager@banwee.com'))
                existing_manager = result.scalar_one_or_none()

                if not existing_manager:
                    users_to_create.append({
                        'email': 'manager@banwee.com',
                        'password': 'Manager123!',
                        'firstname': 'Manager',
                        'lastname': 'User',
                        'role': UserRole.MANAGER,
                        'phone': '+1234567890'
                    })
                else:
                    print(f"✓ Manager user already exists: manager@banwee.com")

            # Support user
            if user_type in ['support', 'all']:
                result = await db.execute(select(User).where(User.email == 'support@banwee.com'))
                existing_support = result.scalar_one_or_none()

                if not existing_support:
                    users_to_create.append({
                        'email': 'support@banwee.com',
                        'password': 'Support123!',
                        'firstname': 'Support',
                        'lastname': 'User',
                        'role': UserRole.SUPPORT,
                        'phone': '+1234567890'
                    })
                else:
                    print(f"✓ Support user already exists: support@banwee.com")

            # Customer user
            if user_type in ['customer', 'all']:
                result = await db.execute(select(User).where(User.email == 'customer@banwee.com'))
                existing_customer = result.scalar_one_or_none()

                if not existing_customer:
                    users_to_create.append({
                        'email': 'customer@banwee.com',
                        'password': 'Customer123!',
                        'firstname': 'Customer',
                        'lastname': 'User',
                        'role': UserRole.CUSTOMER,
                        'phone': '+1234567890'
                    })
                else:
                    print(f"✓ Customer user already exists: customer@banwee.com")
            
            # Create users
            from models.accounts.user import uuid7
            for user_data in users_to_create:
                hashed_password = password_manager.hash_password(user_data['password'])
                
                new_user = User(
                    id=uuid7(),
                    email=user_data['email'],
                    firstname=user_data['firstname'],
                    lastname=user_data['lastname'],
                    hashed_password=hashed_password,
                    role=user_data['role'],
                    phone=user_data['phone'],
                    account_status=AccountStatus.ACTIVE,
                    verification_status=VerificationStatus.VERIFIED
                )
                
                db.add(new_user)
                await db.commit()
                await db.refresh(new_user)
                
                print(f"✅ {user_data['role'].value.capitalize()} user created successfully!")
                print(f"  Email: {user_data['email']}")
                print(f"  Password: {user_data['password']}")
                print(f"  Role: {new_user.role}")
                print(f"  Status: {new_user.account_status}")
                print(f"  Verification: {new_user.verification_status}")
                print()
            
            if not users_to_create:
                print("No new users created (all already exist)")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Get user type from command line argument
    user_type = sys.argv[1] if len(sys.argv) > 1 else 'all'

    # Validate user type
    valid_types = ['guest', 'admin', 'manager', 'support', 'customer', 'all']
    if user_type not in valid_types:
        print("Usage: python add_test_user.py [guest|admin|manager|support|customer|all]")
        print("  guest    - Create only guest user")
        print("  admin    - Create only admin user")
        print("  manager  - Create only manager user")
        print("  support  - Create only support user")
        print("  customer - Create only customer user")
        print("  all      - Create all user types (default)")
        sys.exit(1)

    asyncio.run(add_test_user(user_type))
