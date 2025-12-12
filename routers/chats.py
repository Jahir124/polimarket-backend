# routers/chats.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List

from db import get_session
from auth import get_current_user
from models import Chat, Message, User, Product
from schemas import ChatListItem

router = APIRouter(prefix="/chats", tags=["chats"])


@router.get("/my", response_model=List[ChatListItem])
def get_my_chats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Devuelve todos los chats donde el usuario actual es comprador o vendedor.
    Incluye info básica del producto, buyer, seller y el último mensaje (si existe).
    """

    # 1. Buscar todos los chats donde estoy como buyer o seller
    chats = (
        session.query(Chat)
        .filter(
            or_(
                Chat.buyer_id == current_user.id,
                Chat.seller_id == current_user.id,
            )
        )
        .order_by(Chat.created_at.desc())
        .all()
    )

    resultado: list[ChatListItem] = []

    for chat in chats:
        # Cargar relaciones (depende de cómo tengas configurado lazy/relationships)
        product: Product = chat.product
        buyer: User = chat.buyer
        seller: User = chat.seller

        # Último mensaje de ese chat (si quieres mostrarlo en la lista)
        last_msg = (
            session.query(Message)
            .filter(Message.chat_id == chat.id)
            .order_by(Message.created_at.desc())
            .first()
        )

        resultado.append(
            ChatListItem(
                id=chat.id,
                product=product,
                buyer=buyer,
                seller=seller,
                last_message=last_msg.text if last_msg else None,
            )
        )

    return resultado
