from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from typing import Dict, Set, Optional
from jose import jwt, JWTError
import json
import os
import shutil
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uuid
from dotenv import load_dotenv

# Cargar variables de entorno (.env)
load_dotenv()

from db import init_db, get_session
# Asegúrate de que models.py tenga todas las clases: User, Product, Chat, Message, Order, Favorite, Category
from models import User, Product, Chat, Message, ProductRead, Category, Order, Favorite
from storage import upload_image_to_supabase
from auth import get_current_user, create_token, hash_pwd, verify_pwd, SECRET, ALGO

app = FastAPI(title="PoliMarket")

# --- CONFIGURACIÓN DE CORS (CRUCIAL PARA QUE NO FALLE) ---
origins = [
    "http://localhost:5173",                 # Tu PC Local
    "https://polimarket-kappa.vercel.app",   # Tu Web en Producción
    "https://polimarket-kappa.vercel.app/"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Carpeta para imágenes temporales (si falla Supabase)
os.makedirs("static/images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Inicializar DB al arrancar
@app.on_event("startup")
def on_startup():
    init_db()

# --- 🚨 ATENCIÓN: PON AQUÍ TUS CORREOS REALES DE REPARTIDORES ---
DELIVERY_STAFF = ["tu_correo@espol.edu.ec", "correo_socio@espol.edu.ec"]


# -------------------------
#   MODELOS DE DATOS (PYDANTIC)
# -------------------------
class RegisterBody(BaseModel):
    name: str
    email: str
    password: str

class DeliveryRequest(BaseModel):
    product_id: int
    faculty: str
    building: str
    payment_method: str


# -------------------------
#         AUTENTICACIÓN
# -------------------------

@app.post("/auth/register")
def register(body: RegisterBody, session: Session = Depends(get_session)):
    # Validación simple de dominio
    if not body.email.lower().endswith("@espol.edu.ec"):
        raise HTTPException(400, "Solo se permiten correos @espol.edu.ec")

    # Verificar si ya existe
    if session.exec(select(User).where(User.email == body.email)).first():
        raise HTTPException(400, "Email ya registrado")

    user = User(name=body.name, email=body.email, password_hash=hash_pwd(body.password))
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


# -------------------------
#        USUARIOS
# -------------------------

@app.get("/users")
def list_users(session: Session = Depends(get_session)):
    return session.exec(select(User)).all()

@app.get("/users/{user_id}")
def get_user(user_id: int, session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if not user: raise HTTPException(404, "Usuario no encontrado")
    return user

@app.put("/users/me")
async def update_me(
    name: str = Form(None),
    file: UploadFile = File(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    if name: user.name = name
    if file:
        file_ext = file.filename.split(".")[-1]
        unique_filename = f"avatar_{user.id}_{uuid.uuid4()}.{file_ext}"
        content = await file.read()
        url = upload_image_to_supabase(content, unique_filename, file.content_type)
        if url: user.profile_image = url
        
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

@app.get("/users/{user_id}/products")
def get_user_products(user_id: int, session: Session = Depends(get_session)):
    return session.exec(select(Product).where(Product.seller_id == user_id)).all()

@app.get("/users/me/favorites")
def get_my_favorites(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return user.favorites


# -------------------------
#       PRODUCTOS
# -------------------------

@app.get("/products")
def list_products(session: Session = Depends(get_session)):
    return session.exec(select(Product).order_by(Product.created_at.desc())).all()

@app.get("/products/{pid}")
def product_detail(pid: int, session: Session = Depends(get_session)):
    p = session.get(Product, pid)
    if not p: raise HTTPException(404, "Producto no encontrado")
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
    if not file.content_type.startswith("image/"):
        raise HTTPException(400, "El archivo debe ser una imagen")

    file_ext = file.filename.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{file_ext}"
    content = await file.read()
    image_url = upload_image_to_supabase(content, unique_filename, file.content_type)
    
    if not image_url:
        raise HTTPException(500, "Error subiendo imagen a la nube")

    product = Product(
        title=title, description=description, price=price, category=category,
        image_url=image_url, seller_id=current_user.id
    )
    session.add(product)
    session.commit()
    session.refresh(product)
    return product

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
    if not product: raise HTTPException(404, "Producto no encontrado")
    if product.seller_id != user.id: raise HTTPException(403, "No eres el dueño")
    
    if title: product.title = title
    if description: product.description = description
    if price: product.price = price
    if category: product.category = category
    
    session.add(product)
    session.commit()
    session.refresh(product)
    return product

@app.post("/products/{pid}/favorite")
def toggle_favorite(pid: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    fav = session.get(Favorite, (user.id, pid))
    if fav:
        session.delete(fav)
        session.commit()
        return {"status": "removed"}
    else:
        new_fav = Favorite(user_id=user.id, product_id=pid)
        session.add(new_fav)
        session.commit()
        return {"status": "added"}


# -------------------------
#         CHATS
# -------------------------

@app.post("/chats/start")
def start_chat(product_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    product = session.get(Product, product_id)
    if not product: raise HTTPException(404, "Producto no existe")
    if product.seller_id == user.id: raise HTTPException(400, "No puedes chatear contigo mismo")

    chat = session.exec(select(Chat).where(Chat.product_id == product_id, Chat.buyer_id == user.id)).first()
    if not chat:
        chat = Chat(product_id=product_id, buyer_id=user.id, seller_id=product.seller_id)
        session.add(chat)
        session.commit()
        session.refresh(chat)

    return {"chat_id": chat.id}

@app.get("/chats/my")
def get_my_chats(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    chats = session.exec(select(Chat).where((Chat.buyer_id == user.id) | (Chat.seller_id == user.id)).order_by(Chat.created_at.desc())).all()
    # Forzamos carga de relaciones para el frontend
    for c in chats:
        session.refresh(c.product)
        session.refresh(c.buyer)
        session.refresh(c.seller)
    return chats

@app.get("/chats/{chat_id}/messages")
def get_messages(chat_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    chat = session.get(Chat, chat_id)
    if not chat: raise HTTPException(404, "Chat no encontrado")
    if user.id != chat.buyer_id and user.id != chat.seller_id: raise HTTPException(403, "No autorizado")
    
    return session.exec(select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at.asc())).all()

@app.post("/chats/{chat_id}/confirm_payment")
def confirm_payment(chat_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    chat = session.get(Chat, chat_id)
    if not chat: raise HTTPException(404, "Chat no encontrado")
    if user.id != chat.seller_id: raise HTTPException(403, "Solo el vendedor confirma pagos")

    chat.payment_confirmed = True
    session.add(chat)
    # Mensaje automático
    session.add(Message(chat_id=chat.id, author_id=user.id, text="✅ **PAGO CONFIRMADO**\nComprador: Selecciona 'Recoger' o 'Delivery'."))
    session.commit()
    return {"status": "confirmed"}


# -------------------------
#    DELIVERY / ÓRDENES
# -------------------------

@app.post("/orders/create")
def create_order(req: DeliveryRequest, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    product = session.get(Product, req.product_id)
    if not product: raise HTTPException(404, "Producto no encontrado")

    # Tarifas
    faculty = req.faculty.upper()
    fee = 0.50
    if faculty in ["FCNM", "FIEC", "FIMCP"]: fee = 0.25
    elif faculty == "FCV": fee = 1.00
    
    total = product.price + fee

    order = Order(
        buyer_id=user.id, seller_id=product.seller_id, product_id=product.id,
        faculty=req.faculty, building=req.building, payment_method=req.payment_method,
        status="pending", delivery_fee=fee, total_amount=total
    )
    session.add(order)
    session.commit()
    session.refresh(order)

    # Avisar en chat
    chat = session.exec(select(Chat).where(Chat.product_id == product.id, Chat.buyer_id == user.id)).first()
    if chat:
        msg = f"🛵 **Solicitud de Delivery**\nDestino: {req.faculty}\nTotal: ${total:.2f}\nEstado: Buscando repartidor..."
        session.add(Message(chat_id=chat.id, author_id=user.id, text=msg))
        session.commit()

    return {"order_id": order.id, "fee": fee}

@app.get("/delivery/orders")
def get_pending_orders(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    # Aquí podrías validar si el usuario es delivery staff real
    # if user.email not in DELIVERY_STAFF: raise HTTPException(403)
    return session.exec(select(Order).where(Order.status.in_(["pending", "accepted"])).order_by(Order.created_at.asc())).all()

# --- BUSCA ESTA FUNCIÓN EN TU MAIN.PY Y REEMPLÁZALA ---

@app.put("/delivery/orders/{order_id}")
def update_order_status(order_id: int, status: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    # 1. Validar orden
    order = session.get(Order, order_id)
    if not order: raise HTTPException(404, "Orden no encontrada")
    
    # 2. Actualizar Estado
    order.status = status
    if status == "accepted": 
        # Si alguien más ya la tomó, error
        if order.delivery_person_id is not None and order.delivery_person_id != user.id:
             raise HTTPException(400, "Esta orden ya fue tomada por otro repartidor")
        order.delivery_person_id = user.id
    
    session.add(order)
    session.commit()
    
    # 3. LÓGICA DE CREACIÓN DE CHAT (REPARTIDOR <-> COMPRADOR)
    if status == "accepted":
        # Verificamos si ya existe un chat entre este repartidor y el comprador por este producto
        delivery_chat = session.exec(
            select(Chat).where(
                Chat.product_id == order.product_id,
                Chat.buyer_id == order.buyer_id,
                Chat.seller_id == user.id 
            )
        ).first()

        if not delivery_chat:
            # Creamos el NUEVO CHAT
            delivery_chat = Chat(
                product_id=order.product_id,
                buyer_id=order.buyer_id,   # El comprador original
                seller_id=user.id,         # El repartidor (actúa como "vendedor" del servicio)
                payment_confirmed=True     # Ya está pagado
            )
            session.add(delivery_chat)
            session.commit()
            session.refresh(delivery_chat)

            # Enviamos el mensaje automático en el NUEVO chat
            welcome_msg = (
                f"👋 **¡Hola! Soy {user.name}, tu repartidor.**\n"
                f"He aceptado tu pedido para: {order.faculty} - {order.building}.\n"
                f"Total a cobrar: ${order.total_amount:.2f} ({order.payment_method}).\n"
                f"¡Voy en camino!"
            )
            session.add(Message(chat_id=delivery_chat.id, author_id=user.id, text=welcome_msg))
            session.commit()

        # Opcional: Avisar también en el chat original con el vendedor
        original_chat = session.exec(select(Chat).where(Chat.product_id == order.product_id, Chat.buyer_id == order.buyer_id, Chat.seller_id == order.seller_id)).first()
        if original_chat:
            sys_msg = f"ℹ️ El repartidor **{user.name}** ha aceptado el pedido."
            session.add(Message(chat_id=original_chat.id, author_id=user.id, text=sys_msg))
            session.commit()

    elif status == "completed":
        chat = session.exec(select(Chat).where(Chat.product_id == order.product_id, Chat.buyer_id == order.buyer_id, Chat.seller_id == user.id)).first()
        if chat:
            session.add(Message(chat_id=chat.id, author_id=user.id, text="✅ **Pedido Entregado**\n¡Gracias por usar Polimarket!"))
            session.commit()

    return {"status": "updated"}

# --- AGREGAR EN main.py (SECCIÓN USUARIOS O ÓRDENES) ---

@app.get("/users/me/sales")
def get_my_sales(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Historial de ventas EXITOSAS (completed) del usuario logueado"""
    # Traemos las órdenes donde el usuario es vendedor y el estado es 'completed'
    orders = session.exec(
        select(Order).where(Order.seller_id == user.id, Order.status == "completed").order_by(Order.created_at.desc())
    ).all()
    
    # Cargamos el producto asociado para mostrar nombre y foto
    for o in orders:
        session.refresh(o.product)
    return orders

@app.get("/users/me/purchases")
def get_my_purchases(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Historial de compras EXITOSAS (completed) del usuario logueado"""
    orders = session.exec(
        select(Order).where(Order.buyer_id == user.id, Order.status == "completed").order_by(Order.created_at.desc())
    ).all()
    
    for o in orders:
        session.refresh(o.product)
    return orders



# -------------------------
#       WEBSOCKETS
# -------------------------

async def get_current_user_ws(token: str, session: Session = Depends(get_session)) -> User:
    try:
        data = jwt.decode(token, SECRET, algorithms=[ALGO])
        uid = int(data.get("sub"))
    except:
        raise WebSocketDisconnect(code=1008, reason="Token inválido")
    user = session.get(User, uid)
    if not user: raise WebSocketDisconnect(code=1008, reason="Usuario no encontrado")
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
            await ws.close(code=1008)
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
                    "text": msg.text,
                    "created_at": str(msg.created_at)
                })
        except WebSocketDisconnect:
            manager.disconnect(chat_id, ws)
    finally:
        session.close()