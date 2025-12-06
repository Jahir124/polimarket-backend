from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from typing import Dict, Set
from jose import jwt, JWTError
import json
import os
import shutil
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles # Nuevo
from models import User, Product, Chat, Message # Asegúrate que todos estén

from db import init_db, get_session
from models import User, Product, Chat, Message
from auth import get_current_user, create_token, hash_pwd, verify_pwd, SECRET, ALGO
#PRUEBA GIT

app = FastAPI(title="PoliMarket") # Título actualizado
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

BASE_URL = "http://127.0.0.1:8000"
os.makedirs("static/images", exist_ok=True) # Crea la carpeta si no existe
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
def on_startup():
    init_db()


# ---- AUTH ----
@app.post("/auth/register")
def register(name: str, email: str, password: str, session: Session = Depends(get_session)):
    
    # --- INICIO DE LA VALIDACIÓN ---
    if not email.lower().endswith("@espol.edu.ec"):
        raise HTTPException(
            status_code=400, 
            detail="Registro fallido. Solo se permiten correos de @espol.edu.ec."
        )
    # --- FIN DE LA VALIDACIÓN ---

    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(400, "Email ya usado")
        
    user = User(name=name, email=email, password_hash=hash_pwd(password))
    session.add(user); session.commit(); session.refresh(user)
    return {"id": user.id}


@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == form.username)).first()
    if not user or not verify_pwd(form.password, user.password_hash):
        raise HTTPException(401, "Credenciales inválidas")
    return {"access_token": create_token(user), "token_type": "bearer"}


@app.get("/auth/me", response_model=User) # <-- NUEVO ENDPOINT
def get_me(user: User = Depends(get_current_user)):
    """Devuelve el usuario actualmente autenticado."""
    return user


# ---- PRODUCTS ----
@app.get("/products")
def list_products(session: Session = Depends(get_session)):
    return session.exec(select(Product).order_by(Product.created_at.desc())).all()


@app.get("/products/{pid}")
def product_detail(pid: int, session: Session = Depends(get_session)):
    p = session.get(Product, pid)
    if not p: raise HTTPException(404, "Producto no encontrado")
    return p


@app.post("/products")
def create_product(
    title: str = Form(...), 
    description: str = Form(...), 
    price: float = Form(...), 
    file: UploadFile = File(...), # <-- Acepta un archivo
    user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    # --- Lógica para guardar el archivo ---
    
    # 1. Define dónde guardar el archivo
    file_path = f"static/images/{file.filename}"
    
    # 2. Guarda el archivo en el disco
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close() # Cierra el archivo

    # 3. Crea la URL completa para la base de datos
    # (El frontend en 8080 necesita la URL completa del backend en 8000)
    image_url = f"{BASE_URL}/{file_path}"

    # --- Lógica de la base de datos ---
    p = Product(
        title=title, 
        description=description, 
        price=price, 
        image_url=image_url, # <-- Guarda la nueva URL
        seller_id=user.id
    )
    session.add(p); session.commit(); session.refresh(p)
    return p

# ---- CHATS ----
@app.post("/chats/start")
def start_chat(product_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    product = session.get(Product, product_id)
    if not product: raise HTTPException(404, "Producto no existe")
    if product.seller_id == user.id:
        raise HTTPException(400, "No puedes chatear contigo mismo")
    chat = session.exec(select(Chat).where(Chat.product_id==product_id, Chat.buyer_id==user.id)).first()
    if not chat:
        chat = Chat(product_id=product_id, buyer_id=user.id, seller_id=product.seller_id)
        session.add(chat); session.commit(); session.refresh(chat)
    return {"chat_id": chat.id}


# En backend/main.py, después de la ruta /chats/start

# --- (NUEVO) LISTAR MIS CHATS ---
@app.get("/chats/my")
def get_my_chats(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """
    Obtiene todos los chats donde el usuario es comprador O vendedor.
    Usamos SQLModel con joins explícitos para cargar los detalles.
    """
    statement = (
        select(Chat)
        .where(
            (Chat.buyer_id == user.id) | (Chat.seller_id == user.id)
        )
        .order_by(Chat.created_at.desc())
    )
    chats = session.exec(statement).all()
    
    # Cargamos manualmente las relaciones necesarias que no son automáticas
    # (Esto es para asegurar que 'product' y 'buyer'/'seller' no sean None)
    results = []
    for chat in chats:
        session.refresh(chat.product)
        session.refresh(chat.buyer)
        session.refresh(chat.seller)
        results.append(chat)

    return results


# --- (NUEVO) OBTENER HISTORIAL DE MENSAJES ---
@app.get("/chats/{chat_id}/messages")
def get_message_history(
    chat_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    Obtiene todos los mensajes de un chat específico.
    Primero, verifica que el usuario actual pertenezca a ese chat.
    """
    chat = session.get(Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat no encontrado")
    
    if user.id != chat.buyer_id and user.id != chat.seller_id:
        raise HTTPException(status_code=403, detail="No autorizado para este chat")
    
    # Carga los mensajes ordenados del más antiguo al más nuevo
    statement = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
    )
    messages = session.exec(statement).all()
    return messages



# ---- WEBSOCKET CHAT (AHORA SEGURO) ----

async def get_current_user_ws(token: str, session: Session = Depends(get_session)) -> User:
    """Helper para autenticar usuarios en WebSockets"""
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
async def chat_ws(
    chat_id: int, 
    ws: WebSocket, 
    token: str = Query(...) # <-- Pide token por URL
):
    session = next(get_session())
    try:
        # 1. Autenticar al usuario
        user = await get_current_user_ws(token, session)
        
        # 2. (Opcional) Verificar si el usuario pertenece a este chat
        chat = session.get(Chat, chat_id)
        if not chat or (user.id != chat.buyer_id and user.id != chat.seller_id):
            await ws.close(code=1008, reason="No autorizado para este chat")
            return
            
        await manager.connect(chat_id, ws)
        
        try:
            while True:
                data_str = await ws.receive_text()
                # Espera {"text": "..."}
                data = json.loads(data_str)
                
                # 3. Usar el ID del usuario autenticado (NO EL ID DEL CLIENTE)
                msg = Message(chat_id=chat_id, author_id=user.id, text=data["text"])
                session.add(msg); session.commit(); session.refresh(msg)
                
                await manager.broadcast(chat_id, {
                    "author_id": msg.author_id, 
                    "author_name": user.name, # ¡Bonus!
                    "text": msg.text, 
                    "created_at": str(msg.created_at)
                })
        except WebSocketDisconnect:
            manager.disconnect(chat_id, ws)
    finally:
        session.close()