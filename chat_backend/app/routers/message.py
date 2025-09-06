from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app import models, schemas
from app.schemas.message import MessageResponse
from app.database import get_db
from app.utils.auth import get_current_user  # assumes you already have this
from app.models.user import User

router = APIRouter(prefix="/messages", tags=["Messages"])

# Send a new message
@router.post("/", response_model=MessageResponse)
def send_message(
    message: schemas.message.MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_message = models.message.Message(
        sender_id=current_user.id,
        receiver_id=message.receiver_id,
        content=message.content,
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)
    return new_message


# Get all messages between me and another user
@router.get("/{user_id}", response_model=List[schemas.message.MessageResponse])
def get_conversation(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    messages = (
        db.query(models.message.Message)
        .filter(
            ((models.message.Message.sender_id == current_user.id) & (models.message.Message.receiver_id == user_id))
            | ((models.message.Message.sender_id == user_id) & (models.message.Message.receiver_id == current_user.id))
        )
        .order_by(models.message.Message.timestamp.asc())
        .all()
    )
    return messages
