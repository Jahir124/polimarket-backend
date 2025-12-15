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
    profile_image: Optional[str] = None  # ✅ Añadido
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_delivery: bool = Field(default=False)
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
    id: int
    title: str
    description: str
    price: float
    image_url: str | None = None
    seller_id: int

class Chat(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    buyer_id: int = Field(foreign_key="user.id")
    seller_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    payment_confirmed: bool = Field(default=False)
    
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

# ✅ MODELO ORDER CORREGIDO CON TODOS LOS CAMPOS
class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    buyer_id: int = Field(foreign_key="user.id")
    product_id: int = Field(foreign_key="product.id")
    seller_id: int = Field(foreign_key="user.id")
    
    # Datos de entrega
    faculty: str
    building: str
    classroom: Optional[str] = None
    payment_method: str  # 'Efectivo' o 'Transferencia'
    
    # ✅ CAMPOS QUE FALTABAN
    delivery_person_id: Optional[int] = Field(default=None, foreign_key="user.id")
    delivery_fee: float = Field(default=0.0)
    total_amount: float
    
    status: str = Field(default="pending")  # pending, accepted, rejected, completed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # ✅ RELACIONES COMPLETAS
    product: Optional[Product] = Relationship()
    buyer: Optional[User] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Order.buyer_id"}
    )
    seller: Optional[User] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Order.seller_id"}
    )
    delivery_person: Optional[User] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Order.delivery_person_id"}
    )
