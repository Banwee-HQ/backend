#!/usr/bin/env python3
"""
Delete a specific user by email
"""
import asyncio
from sqlalchemy import text
from core.db import get_db, initialize_db
from core.config import settings

async def delete_specific_user(email: str):
    """Delete a specific user and all related data"""
    print(f"🗑️ Deleting user: {email}")
    
    try:
        # Initialize database
        initialize_db(settings.SQLALCHEMY_DATABASE_URI, settings.ENVIRONMENT == "local")
        print("✅ Database initialized")
        
        async for db in get_db():
            # Get user ID first
            result = await db.execute(
                text("SELECT id, email FROM users WHERE email = :email"),
                {"email": email}
            )
            user = result.fetchone()
            
            if not user:
                print(f"❌ User {email} not found")
                return False
            
            user_id, user_email = user
            print(f"🔍 Found user: {user_email} (ID: {user_id})")
            
            # Delete related records in correct order
            print("📋 Deleting related data...")
            
            # Delete cart items first
            await db.execute(
                text("DELETE FROM cart_items WHERE cart_id IN (SELECT id FROM carts WHERE user_id = :user_id)"),
                {"user_id": str(user_id)}
            )
            
            # Delete cart
            await db.execute(
                text("DELETE FROM carts WHERE user_id = :user_id"),
                {"user_id": str(user_id)}
            )
            
            # Delete addresses
            await db.execute(
                text("DELETE FROM addresses WHERE user_id = :user_id"),
                {"user_id": str(user_id)}
            )
            
            # Delete orders
            await db.execute(
                text("DELETE FROM orders WHERE user_id = :user_id"),
                {"user_id": str(user_id)}
            )
            
            # Delete subscriptions
            await db.execute(
                text("DELETE FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": str(user_id)}
            )
            
            # Delete wishlist items and wishlists
            await db.execute(
                text("DELETE FROM wishlist_items WHERE wishlist_id IN (SELECT id FROM wishlists WHERE user_id = :user_id)"),
                {"user_id": str(user_id)}
            )
            
            await db.execute(
                text("DELETE FROM wishlists WHERE user_id = :user_id"),
                {"user_id": str(user_id)}
            )
            
            # Delete reviews
            await db.execute(
                text("DELETE FROM reviews WHERE user_id = :user_id"),
                {"user_id": str(user_id)}
            )
            
            # Finally delete the user
            result = await db.execute(
                text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": str(user_id)}
            )
            
            await db.commit()
            print(f"✅ Successfully deleted user {user_email}")
            print(f"📊 Total rows affected: {result.rowcount}")
            
            break
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    email = input("Enter email to delete: ")
    if email:
        asyncio.run(delete_specific_user(email))
    else:
        print("❌ No email provided")
