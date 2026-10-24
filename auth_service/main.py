from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta, timezone
import requests
import atexit

app = FastAPI(
    title="Auth Service API",
    description="Микросервис аутентификации. Предоставляет регистрацию, вход по JWT и защиту эндпоинтов.",
    version="1.0.0",
    root_path="/auth",
    docs_url="/docs",
    redoc_url="/redoc"
)

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

@app.post(
    "/register",
    summary="Регистрация нового пользователя",
    description="Принимает username и password, хэширует пароль алгоритмом bcrypt и сохраняет в in-memory хранилище.",
    tags=["Auth"],
    status_code=201,
    responses={
        400: {"description": "Пользователь с таким именем уже существует"}
    }
)
def register(user: regist):
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="Пользователь уже зарегистрирован")

    hashed_password = pwd_context.hash(user.password)
    users_db[user.username] = {"password": hashed_password}

    return {"message": "Успех"}

@app.post(
    "/login",
    summary="Аутентификация (Вход)",
    description="Проверяет учетные данные и возвращает JWT-токен доступа (access_token).",
    tags=["Auth"],
    responses={
        401: {"description": "Неверный логин или пароль"}
    }
)
def login(user: regist):
    if user.username not in users_db:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    stored_user = users_db[user.username]

    if not pwd_context.verify(user.password, stored_user["password"]):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    access_token = create_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get(
    "/me",
    summary="Получить данные текущего пользователя",
    description="Защищенный эндпоинт. Возвращает имя пользователя при наличии валидного JWT-токена в заголовке Authorization.",
    tags=["Auth"],
    responses={
        401: {"description": "Недействительный, просроченный или отсутствующий токен"}
    }
)
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
    try:
        requests.put(f"{CONSUL_URL}/v1/agent/service/register", json=payload)
        print("Сервис auth-1 успешно зарегистрирован в Consul")
    except Exception as e:
        print(f"Ошибка регистрации в Consul: {e}")

def deregister_from_consul():
    try:
        requests.put(f"{CONSUL_URL}/v1/agent/service/deregister/auth-1")
        print("Сервис auth-1 успешно удален из Consul")
    except Exception as e:
        print(f"Ошибка дерегистрации из Consul: {e}")

atexit.register(deregister_from_consul)
register_to_consul()