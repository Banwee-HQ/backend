#!/usr/bin/env python3
"""
Script to check subscriptions for a specific user
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
from models.accounts.user import User
from models.commerce.subscriptions import Subscription
from sqlalchemy import select

# Load environment variables
load_dotenv('.env.dev')

async def check_user_subscriptions(email: str):
    """Check subscriptions for a specific user by email"""
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
            # Get user by email
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

            if not user:
                print(f"❌ User not found: {email}")
                return

            print(f"✓ Found user: {user.email} (ID: {user.id}, Role: {user.role})")

            # Get subscriptions for this user
            result = await db.execute(
                select(Subscription).where(Subscription.user_id == user.id)
            )
            subscriptions = result.scalars().all()

            print(f"\nSubscriptions for {email}:")
            print(f"Total count: {len(subscriptions)}")

            if not subscriptions:
                print("  No subscriptions found")
            else:
                for sub in subscriptions:
                    print(f"\n  Subscription ID: {sub.id}")
                    print(f"  Name: {sub.name}")
                    print(f"  Status: {sub.status}")
                    print(f"  Billing Cycle: {sub.billing_cycle}")
                    print(f"  Auto Renew: {sub.auto_renew}")
                    print(f"  Created At: {sub.created_at}")
                    print(f"  Variant IDs: {sub.variant_ids}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_subscriptions.py <email>")
        sys.exit(1)

    email = sys.argv[1]
    asyncio.run(check_user_subscriptions(email))
