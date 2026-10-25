from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os
import requests
import atexit
import json
import threading
import pika

app = FastAPI(
    title="Order Service API",
    description="Микросервис заказов. Хранит заказы пользователей и интегрируется с GraphQL шлюзом.",
    version="1.0.0",
    root_path="/orders",
    docs_url="/docs",
    redoc_url="/redoc"
)

INSTANCE_ID = os.environ.get("INSTANCE_NAME", "order-1")
#  URL брокера из переменных окружения docker-compose
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")

class OrderItem(BaseModel):
    productId: int
    quantity: int

#Добавлены totalAmount и status
class Order(BaseModel):
    id: int
    userId: str
    createdAt: str
    items: List[OrderItem]
    totalAmount: float = 0.0
    status: str = "PENDING"  # PENDING, CONFIRMED, CANCELLED

# In-memory хранилище с тестовыми данными
orders_db = {
    1: Order(id=1, userId="123", createdAt=datetime.now().isoformat(), items=[OrderItem(productId=1, quantity=2)], totalAmount=1500.00, status="CONFIRMED"),
    2: Order(id=2, userId="123", createdAt=datetime.now().isoformat(), items=[OrderItem(productId=1, quantity=1)], totalAmount=500.00, status="CONFIRMED"),
    3: Order(id=3, userId="456", createdAt=datetime.now().isoformat(), items=[OrderItem(productId=2, quantity=5)], totalAmount=2500.00, status="CANCELLED"),
}

#Счетчик для новых ID
next_order_id = 4

def get_rabbit_connection():
    return pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))

def publish_message(queue_name: str, message_dict: dict):
    try:
        connection = get_rabbit_connection()
        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=json.dumps(message_dict),
            properties=pika.BasicProperties(delivery_mode=2)  # сообщение сохраняется при перезапуске брокера
        )
        connection.close()
        print(f"[Order Service] ✅ Опубликовано в {queue_name}: {message_dict}")
    except Exception as e:
        print(f"[Order Service] ❌ Ошибка публикации в {queue_name}: {e}")

def start_rabbitmq_consumers():
    """Запускает прослушивание очередей в отдельном потоке"""
    try:
        connection = get_rabbit_connection()
        channel = connection.channel()
        
        channel.queue_declare(queue='payment_completed', durable=True)
        channel.queue_declare(queue='payment_failed', durable=True)

        def on_payment_completed(ch, method, properties, body):
            data = json.loads(body)
            order_id = int(data['orderId'])
            print(f"[Order Service] 📥 Получено PaymentCompleted для заказа {order_id}")
            
            # Идемпотентность
            if order_id in orders_db:
                if orders_db[order_id].status == "PENDING":
                    orders_db[order_id].status = "CONFIRMED"
                    print(f"[Order Service] 🔄 Статус заказа {order_id} изменен на CONFIRMED")
                else:
                    print(f"[Order Service] ⚠️ Заказ {order_id} уже не в PENDING (текущий: {orders_db[order_id].status}). Идемпотентность: изменение пропущено.")
            ch.basic_ack(delivery_tag=method.delivery_tag)

        def on_payment_failed(ch, method, properties, body):
            data = json.loads(body)
            order_id = int(data['orderId'])
            reason = data.get('reason', 'Неизвестная ошибка')
            print(f"[Order Service] 📥 Получено PaymentFailed для заказа {order_id}. Запуск компенсации!")
            
            #Компенсация
            if order_id in orders_db:
                if orders_db[order_id].status == "PENDING":
                    orders_db[order_id].status = "CANCELLED"
                    print(f"[Order Service] 🔄 Статус заказа {order_id} изменен на CANCELLED (компенсация)")
                    
                    # Публикуем событие для Notification Service
                    publish_message('order_cancelled', {
                        "orderId": str(order_id),
                        "reason": reason
                    })
                else:
                    print(f"[Order Service] ⚠️ Заказ {order_id} уже не в PENDING. Компенсация не требуется.")
            ch.basic_ack(delivery_tag=method.delivery_tag)

        channel.basic_consume(queue='payment_completed', on_message_callback=on_payment_completed)
        channel.basic_consume(queue='payment_failed', on_message_callback=on_payment_failed)
        
        print("[Order Service] 🐇 Потребитель RabbitMQ запущен и ожидает сообщения...")
        channel.start_consuming()
    except Exception as e:
        print(f"[Order Service] ❌ Ошибка запуска потребителя RabbitMQ: {e}")

@app.get("/orders", summary="Получить заказы пользователя", tags=["Orders"])
def get_orders_by_user_id(userId: str = Query(..., description="ID пользователя")):
    user_orders = [order.dict() for order in orders_db.values() if order.userId == userId]
    return user_orders

@app.get("/orders/{order_id}", summary="Получить конкретный заказ по ID", tags=["Orders"])
def get_order_by_id(order_id: int):
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return orders_db[order_id].dict()

# Эндпоинт создания заказа
class OrderCreate(BaseModel):
    userId: str
    items: List[OrderItem]
    totalAmount: float

@app.post("/orders", summary="Создать новый заказ", tags=["Orders"])
def create_order(order_in: OrderCreate):
    global next_order_id
    new_id = next_order_id
    next_order_id += 1
    
    new_order = Order(
        id=new_id,
        userId=order_in.userId,
        createdAt=datetime.now().isoformat(),
        items=order_in.items,
        totalAmount=order_in.totalAmount,
        status="PENDING"
    )
    orders_db[new_id] = new_order
    print(f"[Order Service] 📝 Заказ {new_id} создан со статусом PENDING")
    
    # Публикация события OrderCreated
    order_created_payload = {
        "orderId": str(new_id),
        "userId": new_order.userId,
        "items": [{"productId": item.productId, "quantity": item.quantity} for item in new_order.items],
        "totalAmount": new_order.totalAmount,
        "createdAt": new_order.createdAt
    }
    publish_message('order_created', order_created_payload)
    
    return {"message": "Заказ создан и отправлен на оплату", "order": new_order.dict()}

CONSUL_URL = "http://consul:8500"

def register_to_consul():
    payload = {"Name": "order-service", "ID": INSTANCE_ID, "Address": "order-service", "Port": 8000}
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

@app.on_event("startup")
def startup_event():
    register_to_consul()
    # Запускаем потребителей RabbitMQ в фоновом потоке, чтобы не блокировать FastAPI
    consumer_thread = threading.Thread(target=start_rabbitmq_consumers, daemon=True)
    consumer_thread.start()