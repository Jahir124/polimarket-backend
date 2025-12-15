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

load_dotenv()

from db import init_db, get_session
from models import User, Product, Chat, Message, ProductRead, Category, Order, Favorite
from storage import upload_image_to_supabase
from auth import get_current_user, create_token, hash_pwd, verify_pwd, SECRET, ALGO, DELIVERY_JOIN_SECRET

app = FastAPI(title="PoliMarket")

# ✅ CORS CORREGIDO
origins = [
    "http://localhost:5173",
    "https://polimarket-kappa.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("static/images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
def on_startup():
    init_db()

# -------------------------
# MODELOS PYDANTIC
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

# ✅ MODELO PARA BECOME DELIVERY
class DeliveryJoinRequest(BaseModel):
    secret_code: str

# ✅ MODELO PARA START CHAT
class StartChatRequest(BaseModel):
    product_id: int

# ✅ MODELO PARA UPDATE ORDER STATUS
class UpdateOrderStatusRequest(BaseModel):
    status: str

# -------------------------
# AUTENTICACIÓN
# -------------------------
@app.post("/auth/register")
def register(body: RegisterBody, session: Session = Depends(get_session)):
    if not body.email.lower().endswith("@espol.edu.ec"):
        raise HTTPException(400, "Solo se permiten correos @espol.edu.ec")
    
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
# USUARIOS
# -------------------------
@app.get("/users")
def list_users(session: Session = Depends(get_session)):
    return session.exec(select(User)).all()

@app.get("/users/{user_id}")
def get_user(user_id: int, session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if not user: 
        raise HTTPException(404, "Usuario no encontrado")
    return user

@app.put("/users/me")
async def update_me(
    name: str = Form(None),
    file: UploadFile = File(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    if name: 
        user.name = name
    
    if file:
        file_ext = file.filename.split(".")[-1]
        unique_filename = f"avatar_{user.id}_{uuid.uuid4()}.{file_ext}"
        content = await file.read()
        url = upload_image_to_supabase(content, unique_filename, file.content_type)
        if url: 
            user.profile_image = url
    
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

# ✅ ENDPOINT PARA BECOME DELIVERY (VALIDADO EN BACKEND)
@app.post("/users/me/become-delivery")
def become_delivery(
    payload: DeliveryJoinRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    if payload.secret_code != DELIVERY_JOIN_SECRET:
        raise HTTPException(403, "Código secreto incorrecto")
    
    if user.is_delivery:
        return user  # Ya es delivery
    
    user.is_delivery = True
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

@app.get("/users/me/sales")
def get_my_sales(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    orders = session.exec(
        select(Order).where(Order.seller_id == user.id, Order.status == "completed").order_by(Order.created_at.desc())
    ).all()
    
    for o in orders:
        session.refresh(o.product)
    
    return orders

@app.get("/users/me/purchases")
def get_my_purchases(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    orders = session.exec(
        select(Order).where(Order.buyer_id == user.id, Order.status == "completed").order_by(Order.created_at.desc())
    ).all()
    
    for o in orders:
        session.refresh(o.product)
    
    return orders

# -------------------------
# PRODUCTOS
# -------------------------
@app.get("/products")
def list_products(session: Session = Depends(get_session)):
    products = session.exec(select(Product).order_by(Product.created_at.desc())).all()
    
    # ✅ Forzar carga del vendedor para cada producto
    for p in products:
        if p.seller_id:
            session.refresh(p.seller)
    
    return products



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
    if not product: 
        raise HTTPException(404, "Producto no encontrado")
    if product.seller_id != user.id: 
        raise HTTPException(403, "No eres el dueño")
    
    if title: product.title = title
    if description: product.description = description
    if price: product.price = price
    if category: product.category = category
    
    session.add(product)
    session.commit()
    session.refresh(product)
    return product
@app.delete("/products/{pid}")
def delete_product(
    pid: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Eliminar un producto (solo el dueño puede hacerlo)"""
    product = session.get(Product, pid)
    if not product:
        raise HTTPException(404, "Producto no encontrado")
    
    # Verificar que el usuario sea el dueño
    if product.seller_id != user.id:
        raise HTTPException(403, "No eres el dueño de este producto")
    
    # Eliminar producto
    session.delete(product)
    session.commit()
    
    return {"status": "deleted", "product_id": pid}


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
# CHATS
# -------------------------
# ✅ CORREGIDO: AHORA RECIBE JSON BODY
@app.post("/chats/start")
def start_chat(body: StartChatRequest, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    product = session.get(Product, body.product_id)
    if not product: 
        raise HTTPException(404, "Producto no existe")
    if product.seller_id == user.id: 
        raise HTTPException(400, "No puedes chatear contigo mismo")
    
    chat = session.exec(select(Chat).where(
        Chat.product_id == body.product_id, 
        Chat.buyer_id == user.id
    )).first()
    
    if not chat:
        chat = Chat(product_id=body.product_id, buyer_id=user.id, seller_id=product.seller_id)
        session.add(chat)
        session.commit()
        session.refresh(chat)
    
    return {"chat_id": chat.id}

@app.get("/chats/my")
def get_my_chats(
    session: Session = Depends(get_session), 
    current_user: User = Depends(get_current_user)
):
    chats = session.exec(
        select(Chat).where(
            (Chat.buyer_id == current_user.id) | (Chat.seller_id == current_user.id)
        ).order_by(Chat.created_at.desc())
    ).all()
    
    # ✅ FORZAR CARGA DE RELACIONES
    for chat in chats:
        # Cargar producto
        if chat.product_id:
            try:
                session.refresh(chat, ["product"])
            except:
                pass
        
        # Cargar comprador
        if chat.buyer_id:
            try:
                session.refresh(chat, ["buyer"])
            except:
                pass
        
        # Cargar vendedor
        if chat.seller_id:
            try:
                session.refresh(chat, ["seller"])
            except:
                pass
    
    return chats


@app.get("/chats/{chat_id}/messages")
def get_messages(chat_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    chat = session.get(Chat, chat_id)
    if not chat: 
        raise HTTPException(404, "Chat no encontrado")
    if user.id != chat.buyer_id and user.id != chat.seller_id: 
        raise HTTPException(403, "No autorizado")
    
    return session.exec(select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at.asc())).all()

@app.post("/chats/{chat_id}/confirm_payment")
def confirm_payment(chat_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    chat = session.get(Chat, chat_id)
    if not chat: 
        raise HTTPException(404, "Chat no encontrado")
    if user.id != chat.seller_id: 
        raise HTTPException(403, "Solo el vendedor confirma pagos")
    
    chat.payment_confirmed = True
    session.add(chat)
    session.add(Message(
        chat_id=chat.id, 
        author_id=user.id, 
        text="✅ **PAGO CONFIRMADO**\nComprador: Selecciona 'Recoger' o 'Delivery'."
    ))
    session.commit()
    
    return {"status": "confirmed"}

# -------------------------
# DELIVERY / ÓRDENES
# -------------------------
@app.post("/orders/create")
def create_order(req: DeliveryRequest, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    product = session.get(Product, req.product_id)
    if not product: 
        raise HTTPException(404, "Producto no encontrado")
    
    faculty = req.faculty.upper()
    fee = 0.50
    if faculty in ["FCNM", "FIEC", "FIMCP"]: 
        fee = 0.25
    elif faculty == "FCV": 
        fee = 1.00
    
    total = product.price + fee
    
    order = Order(
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
    
    session.add(order)
    session.commit()
    session.refresh(order)
    
    chat = session.exec(select(Chat).where(
        Chat.product_id == product.id, 
        Chat.buyer_id == user.id
    )).first()
    
    if chat:
        msg = f"🛵 **Solicitud de Delivery**\nDestino: {req.faculty}\nTotal: ${total:.2f}\nEstado: Buscando repartidor..."
        session.add(Message(chat_id=chat.id, author_id=user.id, text=msg))
        session.commit()
    
    return {"order_id": order.id, "fee": fee}

@app.get("/delivery/orders")
def get_pending_orders(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    # ✅ VALIDACIÓN DE DELIVERY
    if not user.is_delivery:
        raise HTTPException(403, "No estás autorizado como delivery")
    
    return session.exec(
        select(Order).where(Order.status.in_(["pending", "accepted"])).order_by(Order.created_at.asc())
    ).all()

# ✅ CORREGIDO: AHORA RECIBE JSON BODY
@app.put("/delivery/orders/{order_id}")
def update_order_status(
    order_id: int, 
    body: UpdateOrderStatusRequest,
    user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    order = session.get(Order, order_id)
    if not order: 
        raise HTTPException(404, "Orden no encontrada")
    
    status = body.status
    
    order.status = status
    if status == "accepted":
        if order.delivery_person_id is not None and order.delivery_person_id != user.id:
            raise HTTPException(400, "Esta orden ya fue tomada por otro repartidor")
        order.delivery_person_id = user.id
    
    session.add(order)
    session.commit()
    
    if status == "accepted":
        delivery_chat = session.exec(
            select(Chat).where(
                Chat.product_id == order.product_id,
                Chat.buyer_id == order.buyer_id,
                Chat.seller_id == user.id
            )
        ).first()
        
        if not delivery_chat:
            delivery_chat = Chat(
                product_id=order.product_id,
                buyer_id=order.buyer_id,
                seller_id=user.id,
                payment_confirmed=True
            )
            session.add(delivery_chat)
            session.commit()
            session.refresh(delivery_chat)
        
        welcome_msg = (
            f"👋 **¡Hola! Soy {user.name}, tu repartidor.**\n"
            f"He aceptado tu pedido para: {order.faculty} - {order.building}.\n"
            f"Total a cobrar: ${order.total_amount:.2f} ({order.payment_method}).\n"
            f"¡Voy en camino!"
        )
        session.add(Message(chat_id=delivery_chat.id, author_id=user.id, text=welcome_msg))
        session.commit()
        
        original_chat = session.exec(select(Chat).where(
            Chat.product_id == order.product_id, 
            Chat.buyer_id == order.buyer_id, 
            Chat.seller_id == order.seller_id
        )).first()
        
        if original_chat:
            sys_msg = f"ℹ️ El repartidor **{user.name}** ha aceptado el pedido."
            session.add(Message(chat_id=original_chat.id, author_id=user.id, text=sys_msg))
            session.commit()
    
    elif status == "completed":
        chat = session.exec(select(Chat).where(
            Chat.product_id == order.product_id, 
            Chat.buyer_id == order.buyer_id, 
            Chat.seller_id == user.id
        )).first()
        
        if chat:
            session.add(Message(
                chat_id=chat.id, 
                author_id=user.id, 
                text="✅ **Pedido Entregado**\n¡Gracias por usar Polimarket!"
            ))
            session.commit()
    
    return {"status": "updated"}


# -------------------------
# CARGA MASIVA DE PRODUCTOS
# -------------------------
import pandas as pd
from io import BytesIO

@app.post("/products/bulk-upload")
async def bulk_upload_products(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    Subir múltiples productos desde archivo Excel (.xlsx)
    
    Formato esperado del Excel:
    | title | description | price | category | image_url |
    |-------|-------------|-------|----------|-----------|
    """
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "El archivo debe ser Excel (.xlsx o .xls)")
    
    try:
        # Leer archivo Excel
        contents = await file.read()
        df = pd.read_excel(BytesIO(contents))
        
        # Validar columnas requeridas
        required_columns = ['title', 'description', 'price', 'category', 'image_url']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            raise HTTPException(
                400, 
                f"Faltan columnas requeridas: {', '.join(missing_columns)}"
            )
        
        products_created = []
        errors = []
        
        # Procesar cada fila
        for index, row in df.iterrows():
            row_num = index + 2  # +2 porque Excel empieza en 1 y hay header
            
            try:
                # Validaciones
                if pd.isna(row['title']) or not row['title'].strip():
                    errors.append(f"Fila {row_num}: Título vacío")
                    continue
                
                if pd.isna(row['price']) or float(row['price']) <= 0:
                    errors.append(f"Fila {row_num}: Precio inválido")
                    continue
                
                # Validar categoría
                category_value = str(row['category']).lower()
                valid_categories = ['food', 'electronics', 'study', 'other']
                if category_value not in valid_categories:
                    errors.append(
                        f"Fila {row_num}: Categoría '{category_value}' inválida. "
                        f"Usa: {', '.join(valid_categories)}"
                    )
                    continue
                
                # Crear producto
                product = Product(
                    title=str(row['title']).strip(),
                    description=str(row['description']).strip() if not pd.isna(row['description']) else "",
                    price=float(row['price']),
                    category=Category(category_value),
                    image_url=str(row['image_url']).strip() if not pd.isna(row['image_url']) else None,
                    seller_id=current_user.id
                )
                
                session.add(product)
                products_created.append({
                    'row': row_num,
                    'title': product.title
                })
                
            except Exception as e:
                errors.append(f"Fila {row_num}: {str(e)}")
                continue
        
        # Guardar todo en la base de datos
        session.commit()
        
        return {
            "success": True,
            "products_created": len(products_created),
            "products_details": products_created,
            "errors": errors,
            "total_rows": len(df)
        }
        
    except Exception as e:
        raise HTTPException(500, f"Error procesando archivo: {str(e)}")


@app.get("/products/bulk-upload/template")
async def download_template():
    """
    Descargar plantilla Excel de ejemplo
    """
    from fastapi.responses import StreamingResponse
    
    # Crear DataFrame con datos de ejemplo
    sample_data = {
        'title': [
            'Calculadora Científica',
            'Apuntes de Cálculo',
            'Empanada de Queso'
        ],
        'description': [
            'Casio FX-991, casi nueva',
            'Apuntes completos del semestre',
            'Empanada recién hecha'
        ],
        'price': [15.00, 3.50, 1.00],
        'category': ['electronics', 'study', 'food'],
        'image_url': [
            'https://ejemplo.com/calculadora.jpg',
            'https://ejemplo.com/apuntes.jpg',
            'https://ejemplo.com/empanada.jpg'
        ]
    }
    
    df = pd.DataFrame(sample_data)
    
    # Crear archivo Excel en memoria
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Productos')
        
        # Agregar hoja con instrucciones
        instructions = pd.DataFrame({
            'INSTRUCCIONES': [
                '1. Llena cada columna con los datos de tus productos',
                '2. title: Nombre del producto (obligatorio)',
                '3. description: Descripción detallada',
                '4. price: Precio en dólares (número positivo)',
                '5. category: Debe ser: food, electronics, study, o other',
                '6. image_url: URL de la imagen (debe ser pública)',
                '',
                'CATEGORÍAS VÁLIDAS:',
                '- food: Comida y bebidas',
                '- electronics: Electrónicos y gadgets',
                '- study: Útiles y material de estudio',
                '- other: Otros productos',
                '',
                'IMPORTANTE:',
                '- No borres las columnas',
                '- Usa URLs públicas para las imágenes',
                '- El precio debe ser un número (ej: 15.50)',
                '- Elimina las filas de ejemplo antes de subir'
            ]
        })
        instructions.to_excel(writer, index=False, sheet_name='INSTRUCCIONES')
    
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=plantilla_productos_polimarket.xlsx"
        }
    )





# -------------------------
# WEBSOCKETS
# -------------------------
async def get_current_user_ws(token: str, session: Session = Depends(get_session)) -> User:
    try:
        data = jwt.decode(token, SECRET, algorithms=[ALGO])
        uid = int(data.get("sub"))
    except:
        raise WebSocketDisconnect(code=1008, reason="Token inválido")
    
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
            try:
                await ws.send_json(message)
            except:
                self.disconnect(chat_id, ws)

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
