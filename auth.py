from datetime import datetime, timedelta
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.hash import bcrypt
from sqlmodel import Session, select
from db import get_session
from models import User

import os
SECRET = "CHANGE_ME" # cámbialo en producción
ALGO = "HS256"
ACCESS_MINUTES = 60 * 24
DELIVERY_JOIN_SECRET="clod"


oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


# helpers


def hash_pwd(pw: str):
    return bcrypt.hash(pw)


def verify_pwd(pw: str, h: str):
    return bcrypt.verify(pw, h)


def create_token(user: User):
    payload = {"sub": str(user.id), "exp": datetime.utcnow() + timedelta(minutes=ACCESS_MINUTES)}
    return jwt.encode(payload, SECRET, algorithm=ALGO)


async def get_current_user(token: str = Depends(oauth2), session: Session = Depends(get_session)) -> User:
    try:
        data = jwt.decode(token, SECRET, algorithms=[ALGO])
        uid = int(data.get("sub"))
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")
    user = session.get(User, uid)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user