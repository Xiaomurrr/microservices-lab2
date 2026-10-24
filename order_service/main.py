from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os
import requests
import atexit

app = FastAPI(
    title="Order Service API",
    description="Микросервис заказов. Хранит заказы пользователей и интегрируется с GraphQL шлюзом.",
    version="1.0.0",
    root_path="/orders",
    docs_url="/docs",
    redoc_url="/redoc"
)

INSTANCE_ID = os.environ.get("INSTANCE_NAME", "order-1")

class OrderItem(BaseModel):
    productId: int
    quantity: int

class Order(BaseModel):
    id: int
    userId: str
    createdAt: str
    items: List[OrderItem]

#In-memory хранилище с тестовыми данными
orders_db = {
    1: Order(
        id=1,
        userId="123",
        createdAt=datetime.now().isoformat(),
        items=[
            OrderItem(productId=1, quantity=2),
            OrderItem(productId=2, quantity=1)
        ]
    ),
    2: Order(
        id=2,
        userId="123",
        createdAt=datetime.now().isoformat(),
        items=[
            OrderItem(productId=1, quantity=1)
        ]
    ),
    3: Order(
        id=3,
        userId="456",
        createdAt=datetime.now().isoformat(),
        items=[
            OrderItem(productId=2, quantity=5)
        ]
    )
}

@app.get(
    "/orders",
    summary="Получить заказы пользователя",
    description="Возвращает список заказов для указанного userId. Содержит только productId",
    tags=["Orders"],
    responses={
        200: {"description": "Список заказов пользователя"},
        404: {"description": "Заказы для данного пользователя не найдены"}
    }
)
def get_orders_by_user_id(userId: str = Query(..., description="ID пользователя")):
    user_orders = [order.dict() for order in orders_db.values() if order.userId == userId]
    if not user_orders:
        return [] 
    return user_orders

@app.get(
    "/orders/{order_id}",
    summary="Получить конкретный заказ по ID",
    description="Возвращает детали конкретного заказа.",
    tags=["Orders"],
    responses={
        404: {"description": "Заказ не найден"}
    }
)
def get_order_by_id(order_id: int):
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return orders_db[order_id].dict()


CONSUL_URL = "http://consul:8500"

def register_to_consul():
    payload = {
        "Name": "order-service",
        "ID": INSTANCE_ID,
        "Address": "order-service", # DNS-имя контейнера в docker network
        "Port": 8000
    }
    try:
        requests.put(f"{CONSUL_URL}/v1/agent/service/register", json=payload)
        print(f"Сервис {INSTANCE_ID} успешно зарегистрирован в Consul")
    except Exception as e:
        print(f"Ошибка регистрации в Consul: {e}")

def deregister_from_consul():
    try:
        requests.put(f"{CONSUL_URL}/v1/agent/service/deregister/{INSTANCE_ID}")
        print(f"Сервис {INSTANCE_ID} успешно удален из Consul")
    except Exception as e:
        print(f"Ошибка дерегистрации из Consul: {e}")

atexit.register(deregister_from_consul)
register_to_consul()