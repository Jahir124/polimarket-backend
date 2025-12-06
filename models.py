from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(index=True, unique=True)
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    products: list["Product"] = Relationship(back_populates="seller")


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str
    price: float
    image_url: str  # <-- CAMBIO AÑADIDO
    seller_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    seller: Optional[User] = Relationship(back_populates="products")


# En backend/models.py

# ... (tus otros imports y clases User/Product) ...

class Chat(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    buyer_id: int = Field(foreign_key="user.id")
    seller_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # --- RELACIONES AÑADIDAS ---
    product: Optional[Product] = Relationship()
    buyer: Optional[User] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Chat.buyer_id"}
    )
    seller: Optional[User] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Chat.seller_id"}
    )
    messages: list["Message"] = Relationship()


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(foreign_key="chat.id")
    author_id: int = Field(foreign_key="user.id")
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

