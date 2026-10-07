from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta

app = FastAPI()

pwd_context = CryptContext(schemes = ["bcrypt"], deprecated="auto")

users_db = {}

SECRET_KEY = "8dq2fdw1klsA"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

class regist(BaseModel):
    username: str
    password: str

@app.post("/register")
def register(user: regist):
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="Пользоваель уже харегистрирован")

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
