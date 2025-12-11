from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from typing import Dict, Set
from jose import jwt, JWTError
import json
import os
import shutil
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel   # <--- IMPORTANTE

import uuid

from dotenv import load_dotenv



# Cargar variables del archivo .env (solo funcionará en tu PC)
load_dotenv()


from db import init_db, get_session
from models import User, Product, Chat, Message, ProductRead, Category, Favorite, Order
from storage import upload_image_to_supabase
from auth import get_current_user, create_token, hash_pwd, verify_pwd, SECRET, ALGO

app = FastAPI(title="PoliMarket")

origins = [
    "http://localhost:5173", #Local development
    "https://polimarket-kappa.vercel.app" # Production
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL = "https://api-polimarket.onrender.com" # BASE_URL = "http://127.0.0.1:8000" for development
os.makedirs("static/images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
def on_startup():
    init_db()


# -------------------------
#   Pydantic model JSON
# -------------------------
class RegisterBody(BaseModel):
    name: str
    email: str
    password: str


# -------------------------
#        AUTH
# -------------------------

@app.post("/auth/register")
def register(body: RegisterBody, session: Session = Depends(get_session)):

    name = body.name
    email = body.email
    password = body.password

    # Validación de correo
    if not email.lower().endswith("@espol.edu.ec"):
        raise HTTPException(
            status_code=400,
            detail="Registro fallido. Solo se permiten correos @espol.edu.ec"
        )

    # Verificar si existe
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(400, "Email ya usado")

    user = User(name=name, email=email, password_hash=hash_pwd(password))
    session.add(user)
    session.commit()
    session.refresh(user)

    return {"id": user.id}


@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == form.username)).first()
    if not user or not verify_pwd(form.password, user.password_hash):
        raise HTTPException(401, "Credenciales inválidas")
    return {"access_token": create_token(user), "token_type": "bearer"}


@app.get("/auth/me", response_model=User)
def get_me(user: User = Depends(get_current_user)):
    return user

# ---- USERS ----

@app.get("/users")
def list_users(session: Session = Depends(get_session)):
    """Lista TODOS los usuarios (útil para pruebas o modo admin)."""
    return session.exec(select(User)).all()


@app.get("/users/{user_id}")
def get_user(user_id: int, session: Session = Depends(get_session)):
    """Obtiene un usuario por ID."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


@app.get("/users/{user_id}/products")
def get_user_products(user_id: int, session: Session = Depends(get_session)):
    """Obtiene todos los productos publicados por un usuario."""
    statement = select(Product).where(Product.seller_id == user_id)
    return session.exec(statement).all()


# -------------------------
#       PRODUCTS
# -------------------------

@app.get("/products")
def list_products(session: Session = Depends(get_session)):
    return session.exec(select(Product).order_by(Product.created_at.desc())).all()


@app.get("/products/{pid}")
def product_detail(pid: int, session: Session = Depends(get_session)):
    p = session.get(Product, pid)
    if not p:
        raise HTTPException(404, "Producto no encontrado")
    return p


@app.post("/products", response_model=ProductRead)
async def create_product(
    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    category: Category = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    # Validamos que sea imagen
    if not file.content_type.startswith("image/"):
        raise HTTPException(400, detail="File must be an image")

    # Creamos nombre único
    file_ext = file.filename.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{file_ext}"

    # Leemos el archivo
    content = await file.read()

    # --- AQUÍ OCURRE LA MAGIA ---
    # Subimos a Supabase en lugar de guardar en disco local
    image_url = upload_image_to_supabase(content, unique_filename, file.content_type)
    
    if not image_url:
        raise HTTPException(500, detail="Failed to upload image to cloud storage")
    # -----------------------------

    # Guardamos en la Base de Datos (Postgres)
    product = Product(
        title=title,
        description=description,
        price=price,
        category=category,
        image_url=image_url,
        seller_id=current_user.id
    )
    
    session.add(product)
    session.commit()
    session.refresh(product)
    return product



# -------------------------
#         CHATS
# -------------------------

@app.post("/chats/start")
def start_chat(product_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Producto no existe")

    if product.seller_id == user.id:
        raise HTTPException(400, "No puedes chatear contigo mismo")

    chat = session.exec(select(Chat).where(Chat.product_id == product_id, Chat.buyer_id == user.id)).first()

    if not chat:
        chat = Chat(product_id=product_id, buyer_id=user.id, seller_id=product.seller_id)
        session.add(chat)
        session.commit()
        session.refresh(chat)

    return {"chat_id": chat.id}


@app.get("/chats/my")
def get_my_chats(user: User = Depends(get_current_user), session: Session = Depends(get_session)):

    statement = (
        select(Chat)
        .where((Chat.buyer_id == user.id) | (Chat.seller_id == user.id))
        .order_by(Chat.created_at.desc())
    )

    chats = session.exec(statement).all()

    results = []
    for chat in chats:
        session.refresh(chat.product)
        session.refresh(chat.buyer)
        session.refresh(chat.seller)
        results.append(chat)

    return results



@app.get("/chats/{chat_id}/messages")
def get_message_history(chat_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):

    chat = session.get(Chat, chat_id)

    if not chat:
        raise HTTPException(404, "Chat no encontrado")

    if user.id != chat.buyer_id and user.id != chat.seller_id:
        raise HTTPException(403, "No autorizado para este chat")

    statement = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
    )
    return session.exec(statement).all()



# -------------------------
#       WEBSOCKETS
# -------------------------

async def get_current_user_ws(token: str, session: Session = Depends(get_session)) -> User:
    try:
        data = jwt.decode(token, SECRET, algorithms=[ALGO])
        uid = int(data.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise WebSocketDisconnect(code=1008, reason="Token inválido o expirado")

    user = session.get(User, uid)
    if not user:
        raise WebSocketDisconnect(code=1008, reason="Usuario no encontrado")
    return user


class ConnectionManager:
    def __init__(self):
        self.rooms: Dict[int, Set[WebSocket]] = {}

    async def connect(self, chat_id: int, ws: WebSocket):
        await ws.accept()
        self.rooms.setdefault(chat_id, set()).add(ws)

    def disconnect(self, chat_id: int, ws: WebSocket):
        self.rooms.get(chat_id, set()).discard(ws)

    async def broadcast(self, chat_id: int, message: dict):
        for ws in list(self.rooms.get(chat_id, set())):
            await ws.send_json(message)


manager = ConnectionManager()


@app.websocket("/ws/chats/{chat_id}")
async def chat_ws(chat_id: int, ws: WebSocket, token: str = Query(...)):

    session = next(get_session())

    try:
        user = await get_current_user_ws(token, session)

        chat = session.get(Chat, chat_id)
        if not chat or (user.id != chat.buyer_id and user.id != chat.seller_id):
            await ws.close(code=1008, reason="No autorizado para este chat")
            return

        await manager.connect(chat_id, ws)

        try:
            while True:
                data = await ws.receive_json()

                msg = Message(chat_id=chat_id, author_id=user.id, text=data["text"])
                session.add(msg)
                session.commit()
                session.refresh(msg)

                await manager.broadcast(chat_id, {
                    "author_id": msg.author_id,
                    "author_name": user.name,
                    "text": msg.text,
                    "created_at": str(msg.created_at)
                })

        except WebSocketDisconnect:
            manager.disconnect(chat_id, ws)

    finally:
        session.close()



# En main.py

# --- FAVORITOS ---
@app.post("/products/{pid}/favorite")
def toggle_favorite(pid: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    # Buscar si ya existe
    fav = session.get(Favorite, (user.id, pid))
    if fav:
        session.delete(fav) # Si existe, lo quita (toggle)
        session.commit()
        return {"status": "removed"}
    else:
        new_fav = Favorite(user_id=user.id, product_id=pid)
        session.add(new_fav)
        session.commit()
        return {"status": "added"}

@app.get("/users/me/favorites")
def get_my_favorites(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    # Devuelve los productos favoritos del usuario
    return user.favorites

# --- EDITAR PRODUCTO ---
@app.put("/products/{pid}")
def update_product(
    pid: int, 
    title: str = Form(None), 
    description: str = Form(None), 
    price: float = Form(None),
    category: str = Form(None),
    user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    product = session.get(Product, pid)
    if not product:
        raise HTTPException(404, "Producto no encontrado")
    if product.seller_id != user.id:
        raise HTTPException(403, "No eres el dueño de este producto")
    
    # Actualizar solo si envían datos
    if title: product.title = title
    if description: product.description = description
    if price: product.price = price
    if category: product.category = category
    
    session.add(product)
    session.commit()
    session.refresh(product)
    return product



class DeliveryRequest(BaseModel):
    product_id: int
    faculty: str
    building: str
    payment_method: str # 'Efectivo' o 'Transferencia'

@app.post("/orders/create")
def create_delivery_order(
    req: DeliveryRequest, 
    user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    product = session.get(Product, req.product_id)
    if not product: raise HTTPException(404, "Producto no encontrado")

    # --- LÓGICA DE TARIFAS ---
    # Normalizamos el texto (mayúsculas) para evitar errores
    faculty = req.faculty.upper()
    
    # Tabla de precios
    fee = 0.50 # Precio default (FCSH, CELEX, FADCOM, Otros)
    
    if faculty in ["FCNM", "FIEC", "FIMCP"]:
        fee = 0.25
    elif faculty == "FCV":
        fee = 1.00
    
    total = product.price + fee

    # Crear orden
    new_order = Order(
        buyer_id=user.id,
        seller_id=product.seller_id,
        product_id=product.id,
        faculty=req.faculty,
        building=req.building,
        payment_method=req.payment_method,
        status="pending",
        delivery_fee=fee,
        total_amount=total
    )
    session.add(new_order)
    session.commit()
    session.refresh(new_order)

    # 1. Avisar en el chat con el VENDEDOR
    chat_seller = session.exec(select(Chat).where(Chat.product_id == product.id, Chat.buyer_id == user.id)).first()
    if chat_seller:
        # El mensaje que pediste:
        auto_text = f"🛵 **Un repartidor recogerá mi pedido**\nOrden #{new_order.id} creada."
        session.add(Message(chat_id=chat_seller.id, author_id=user.id, text=auto_text))
        session.commit()

    return {"order_id": new_order.id, "fee": fee}




# --- EN main.py ---

# 1. Definir quiénes son los Delivery (PON AQUÍ TUS CORREOS REALES)
DELIVERY_STAFF = ["mianmeji@espol.edu.ec", "cjustamond@espol.edu.ec"]

# 2. Endpoint para editar el propio perfil
@app.put("/users/me")
async def update_me(
    name: str = Form(None),
    file: UploadFile = File(None), # Opcional: Nueva foto
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    if name:
        user.name = name
    
    if file:
        # Reusamos tu lógica de subir imagen a Supabase
        file_ext = file.filename.split(".")[-1]
        unique_filename = f"avatar_{user.id}_{uuid.uuid4()}.{file_ext}"
        content = await file.read()
        image_url = upload_image_to_supabase(content, unique_filename, file.content_type)
        if image_url:
            user.profile_image = image_url

    session.add(user)
    session.commit()
    session.refresh(user)
    return user

# 3. Endpoint para Delivery: Ver pedidos pendientes (Solo Staff)
@app.get("/delivery/orders")
def get_pending_orders(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if user.email not in DELIVERY_STAFF:
        raise HTTPException(403, "No eres parte del equipo de Delivery")
    
    # Traemos órdenes pendientes o en proceso
    statement = select(Order).where(Order.status.in_(["pending", "accepted"])).order_by(Order.created_at.asc())
    orders = session.exec(statement).all()
    return orders

# 4. Endpoint para Delivery: Cambiar estado (Aceptar/Entregar)
@app.put("/delivery/orders/{order_id}")
def update_order_status(
    order_id: int, 
    status: str, # "accepted" o "completed"
    user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    if user.email not in DELIVERY_STAFF:
        raise HTTPException(403, "Acceso denegado")
    
    order = session.get(Order, order_id)
    if not order: raise HTTPException(404, "Orden no encontrada")
    
    order.status = status
    session.add(order)
    session.commit()
    return {"status": "updated"}



@app.post("/chats/{chat_id}/confirm_payment")
def confirm_payment(chat_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    chat = session.get(Chat, chat_id)
    if not chat: raise HTTPException(404, "Chat no encontrado")
    
    # Solo el VENDEDOR puede confirmar el pago
    if user.id != chat.seller_id:
        raise HTTPException(403, "Solo el vendedor puede confirmar el pago")

    chat.payment_confirmed = True
    session.add(chat)
    
    # Avisar en el chat automáticamente
    sys_msg = Message(chat_id=chat.id, author_id=user.id, text="✅ **PAGO RECIBIDO CONFIRMADO**\nComprador: Por favor selecciona cómo quieres recibir tu producto.")
    session.add(sys_msg)
    
    session.commit()
    return {"status": "confirmed"}