from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from passlib.context import CryptContext

app = FastAPI()

pwd_context = CryptContext(schemes = ["bcrypt"], deprecated="auto")

users_db = {}

class regist(BaseModel):
    username: str
    password: str