from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
import requests
import atexit

app = FastAPI(
    title="Catalog Service API",
    description="Микросервис каталога товаров. Предоставляет CRUD-операции и интегрируется с GraphQL шлюзом.",
    version="1.0.0",
    root_path="/catalog",
    docs_url="/docs",  # Swagger доступен по /docs
    redoc_url="/redoc" # Альтернативная документация
)

INSTANCE_ID = os.environ.get("INSTANCE_NAME", "catalog-1")

products_db = {}
next_id = 1

class ProductCreate(BaseModel):
    name: str
    price: float
    description: Optional[str] = None

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None

@app.get(
    "/products",
    summary="Получить список всех товаров",
    description="Возвращает массив всех доступных товаров и ID текущего инстанса сервиса (для проверки работы балансировщика Nginx).",
    tags=["Catalog"]
)
def get_products():
    return {
        "instance_id": INSTANCE_ID,
        "products": list(products_db.values())
    }

@app.get(
    "/products/{product_id}",
    summary="Получить товар по ID",
    description="Возвращает детальную информацию о конкретном товаре. Критически важно для агрегации данных в GraphQL шлюзе.",
    tags=["Catalog"],
    responses={
        404: {"description": "Товар с указанным ID не найден"}
    }
)
def get_product_by_id(product_id: int):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return products_db[product_id]

@app.post(
    "/products",
    summary="Создать новый товар",
    description="Добавляет новый товар в каталог. Уникальный ID генерируется автоматически.",
    tags=["Catalog"],
    status_code=201
)
def create_product(product: ProductCreate):
    global next_id

    new_product = {
        "id": next_id,
        "name": product.name,
        "price": product.price,
        "description": product.description
    }
    
    products_db[next_id] = new_product
    next_id += 1
    
    return new_product

@app.put(
    "/products/{product_id}",
    summary="Обновить данные товара",
    description="Частичное или полное обновление полей товара (name, price, description).",
    tags=["Catalog"],
    responses={
        404: {"description": "Товар с указанным ID не найден"}
    }
)
def update_product(product_id: int, product: ProductUpdate):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    existing_product = products_db[product_id]
    update_data = product.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        existing_product[key] = value

    return existing_product

@app.delete(
    "/products/{product_id}",
    summary="Удалить товар",
    description="Удаляет товар из каталога по его уникальному идентификатору.",
    tags=["Catalog"],
    responses={
        404: {"description": "Товар с указанным ID не найден"}
    }
)
def delete_product(product_id: int):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    del products_db[product_id]
    
    return {"message": "Товар удален"}

CONSUL_URL = "http://consul:8500"

def register_to_consul():
    payload = {
        "Name": "catalog-service",
        "ID": INSTANCE_ID,
        "Address": "catalog-service", # DNS-имя контейнера в docker network
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