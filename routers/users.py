# routers/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_session
from auth import get_current_user
from models import User
from schemas import UserPublic, DeliveryJoinRequest
import os

router = APIRouter(prefix="/users", tags=["users"])

# Código secreto configurable
DELIVERY_JOIN_SECRET = os.getenv("DELIVERY_JOIN_SECRET", "CAMBIA_ESTE_CODIGO")


@router.post("/me/become-delivery", response_model=UserPublic)
def become_delivery(
    payload: DeliveryJoinRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Marca al usuario autenticado como delivery si provee el código secreto correcto.
    """

    if payload.secret_code != DELIVERY_JOIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Código secreto incorrecto."
        )

    if current_user.is_delivery:
        return current_user  # Ya era delivery

    current_user.is_delivery = True
    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    return current_user
