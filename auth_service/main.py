from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta, timezone
import requests
import atexit

app = FastAPI(root_path="/auth")

security = HTTPBearer()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

users_db = {}

SECRET_KEY = "8dq2fdw1klsA"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

class regist(BaseModel):
    username: str
    password: str

@app.post("/register")
def register(user: regist):
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="Пользователь уже зарегистрирован")

    hashed_password = pwd_context.hash(user.password)

    users_db[user.username] = {"password": hashed_password}

    return {"message": "Успех"}

@app.post("/login")
def login(user: regist):
    if user.username not in users_db:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    stored_user = users_db[user.username]

    if not pwd_context.verify(user.password, stored_user["password"]):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    access_token = create_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/me")
def get_me(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Недействительный токен")

    username = payload.get("sub")

    if username is None:
        raise HTTPException(status_code=401, detail="Недействительный токен")

    return {"username": username, "message": "Успешная авторизация"}


CONSUL_URL = "http://consul:8500"

def register_to_consul():
    payload = {
        "Name": "auth-service",
        "ID": "auth-1",
        "Address": "auth-service",
        "Port": 8000
    }
    requests.put(f"{CONSUL_URL}/v1/agent/service/register", json=payload)

def deregister_from_consul():
    requests.put(f"{CONSUL_URL}/v1/agent/service/deregister/auth-1")

atexit.register(deregister_from_consul)
register_to_consul()