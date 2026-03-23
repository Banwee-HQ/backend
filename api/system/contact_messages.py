"""
Contact Messages API
Endpoints for contact message management
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
import math

from core.db import get_db
from core.dependencies import get_current_user, require_admin
from schemas.contact_message import (
    ContactMessageCreate,
    ContactMessageUpdate,
    ContactMessageResponse,
    ContactMessageListResponse,
    MessageStatus,
    MessagePriority
)
from core.utils.response import Response
from core.errors import APIException
from services.contact_message import ContactMessageService
from core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/contact-messages", tags=["Contact Messages"])


@router.post("")
async def create_contact_message(
    message_data: ContactMessageCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new contact message (public endpoint)
    """
    try:
        message = await ContactMessageService.create_message(db, message_data)
        return Response.success(
            data={
                "id": str(message.id),
                "name": message.name,
                "email": message.email,
                "subject": message.subject,
                "message": message.message,
                "status": message.status,
                "priority": message.priority,
                "admin_notes": message.admin_notes,
                "assigned_to": str(message.assigned_to) if message.assigned_to else None,
                "created_at": message.created_at.isoformat() if hasattr(message.created_at, 'isoformat') else str(message.created_at),
                "updated_at": message.updated_at.isoformat() if hasattr(message.updated_at, 'isoformat') else str(message.updated_at),
                "resolved_at": message.resolved_at.isoformat() if message.resolved_at and hasattr(message.resolved_at, 'isoformat') else str(message.resolved_at) if message.resolved_at else None
            },
            message="Contact message created successfully",
            status_code=status.HTTP_201_CREATED
        )
    except Exception as e:
        logger.error(f"Error creating contact message: {str(e)}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to create contact message {str(e)}"
        )


@router.get("")
async def get_all_contact_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[MessageStatus] = Query(None, alias="status"),
    priority: Optional[MessagePriority] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_admin)
):
    """
    Get all contact messages with pagination and filters (admin only)
    """
    try:
        messages, total = await ContactMessageService.get_all_messages(
            db=db,
            page=page,
            page_size=page_size,
            status=status_filter,
            priority=priority,
            search=search
        )
        
        logger.info(f"Fetched {len(messages)} messages, total: {total}")
        
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        
        return Response.success(
            data={
                "messages": [
                    {
                        "id": str(msg.id),
                        "name": msg.name,
                        "email": msg.email,
                        "subject": msg.subject,
                        "message": msg.message,
                        "status": msg.status,
                        "priority": msg.priority,
                        "admin_notes": msg.admin_notes,
                        "assigned_to": str(msg.assigned_to) if msg.assigned_to else None,
                        "created_at": msg.created_at.isoformat() if hasattr(msg.created_at, 'isoformat') else str(msg.created_at),
                        "updated_at": msg.updated_at.isoformat() if hasattr(msg.updated_at, 'isoformat') else str(msg.updated_at),
                        "resolved_at": msg.resolved_at.isoformat() if msg.resolved_at and hasattr(msg.resolved_at, 'isoformat') else str(msg.resolved_at) if msg.resolved_at else None
                    }
                    for msg in messages
                ]
            },
            message="Contact messages retrieved successfully",
            pagination={
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages
            }
        )
    except Exception as e:
        logger.error(f"Error fetching contact messages: {str(e)}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch contact messages {str(e)}"
        )


@router.get("/{message_id}")
async def get_contact_message(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_admin)
):
    """
    Get a specific contact message by ID (admin only)
    """
    message = await ContactMessageService.get_message_by_id(db, message_id)
    
    if not message:
        raise APIException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Contact message not found"
        )
    
    return Response.success(
        data={
            "id": str(message.id),
            "name": message.name,
            "email": message.email,
            "subject": message.subject,
            "message": message.message,
            "status": message.status,
            "priority": message.priority,
            "admin_notes": message.admin_notes,
            "assigned_to": str(message.assigned_to) if message.assigned_to else None,
            "created_at": message.created_at.isoformat() if hasattr(message.created_at, 'isoformat') else str(message.created_at),
            "updated_at": message.updated_at.isoformat() if hasattr(message.updated_at, 'isoformat') else str(message.updated_at),
            "resolved_at": message.resolved_at.isoformat() if message.resolved_at and hasattr(message.resolved_at, 'isoformat') else str(message.resolved_at) if message.resolved_at else None
        },
        message="Contact message retrieved successfully"
    )


@router.patch("/{message_id}")
async def update_contact_message(
    message_id: UUID,
    update_data: ContactMessageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_admin)
):
    """
    Update a contact message (admin only)
    """
    try:
        message = await ContactMessageService.update_message(db, message_id, update_data)
        
        if not message:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Contact message not found"
            )
        
        return Response.success(
            data={
                "id": str(message.id),
                "name": message.name,
                "email": message.email,
                "subject": message.subject,
                "message": message.message,
                "status": message.status,
                "priority": message.priority,
                "admin_notes": message.admin_notes,
                "assigned_to": str(message.assigned_to) if message.assigned_to else None,
                "created_at": message.created_at.isoformat() if hasattr(message.created_at, 'isoformat') else str(message.created_at),
                "updated_at": message.updated_at.isoformat() if hasattr(message.updated_at, 'isoformat') else str(message.updated_at),
                "resolved_at": message.resolved_at.isoformat() if message.resolved_at and hasattr(message.resolved_at, 'isoformat') else str(message.resolved_at) if message.resolved_at else None
            },
            message="Contact message updated successfully"
        )
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error updating contact message: {str(e)}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to update contact message"
        )


@router.delete("/{message_id}")
async def delete_contact_message(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_admin)
):
    """
    Delete a contact message (admin only)
    """
    try:
        success = await ContactMessageService.delete_message(db, message_id)
        
        if not success:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Contact message not found"
            )
        
        return Response.success(
            message="Contact message deleted successfully"
        )
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error deleting contact message: {str(e)}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to delete contact message"
        )
