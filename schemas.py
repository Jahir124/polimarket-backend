# schemas.py
from pydantic import BaseModel
from typing import Optional, List


# -------------------------
# Public User Model
# -------------------------
class UserPublic(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    profile_image: Optional[str] = None
    is_delivery: bool = False

    class Config:
        from_attributes = True


# -------------------------
# Product Public Model
# -------------------------
class ProductPublic(BaseModel):
    id: int
    title: str
    image_url: Optional[str]

    class Config:
        from_attributes = True


# -------------------------
# Chats
# -------------------------
class ChatListItem(BaseModel):
    id: int
    product: ProductPublic
    buyer: UserPublic
    seller: UserPublic
    last_message: Optional[str] = None

    class Config:
        from_attributes = True


# -------------------------
# Delivery Join Request
# -------------------------
class DeliveryJoinRequest(BaseModel):
    secret_code: str
