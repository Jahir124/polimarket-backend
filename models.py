from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
import uuid

from enum import Enum


class Favorite(SQLModel, table=True):
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    product_id: int = Field(foreign_key="product.id", primary_key=True)

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(index=True, unique=True)
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    products: list["Product"] = Relationship(back_populates="seller")
    favorites: list["Product"] = Relationship(link_model=Favorite)





class Category(str, Enum):
    FOOD = "food"
    ELECTRONICS = "electronics"
    STUDY = "study"
    OTHER = "other"


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str
    price: float
    category: Category = Field(default=Category.OTHER)
    image_url: Optional[str] = None 
    seller_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    seller: Optional[User] = Relationship(back_populates="products")

class ProductRead(SQLModel):
    id: int  # O uuid.UUID si estás usando UUIDs como primary key
    title: str
    description: str
    price: float
    image_url: str | None = None
    seller_id: int # O el tipo de dato que uses para el ID del usuari
# En backend/models.py

# ... (tus otros imports y clases User/Product) ...

class Chat(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    buyer_id: int = Field(foreign_key="user.id")
    seller_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    payment_confirmed: bool = Field(default=False)
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





# ... (tus otros modelos arriba: Category, Favorite, User, etc.)

class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    buyer_id: int = Field(foreign_key="user.id")
    product_id: int = Field(foreign_key="product.id")
    seller_id: int = Field(foreign_key="user.id")
    
    # Datos de entrega
    faculty: str
    building: str
    classroom: Optional[str] = None # Opcional: Aula
    payment_method: str # 'cash' (Efectivo) o 'transfer' (Transferencia)
    
    status: str = Field(default="pending") # pending, accepted, rejected, completed
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relaciones (opcional, por si quieres expandir luego)
    product: Optional[Product] = Relationship()