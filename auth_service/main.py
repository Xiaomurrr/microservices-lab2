from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from passlib.context import CryptContext

app = FastAPI()

pwd_context = CryptContext(schemes = ["bcrypt"], deprecated="auto")

users_db = {}

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