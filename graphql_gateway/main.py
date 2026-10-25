import asyncio
from contextlib import asynccontextmanager
from typing import List, Optional
import os
import requests
import atexit
import httpx
import strawberry
from fastapi import FastAPI, Request
from strawberry.dataloader import DataLoader
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

CATALOG_SERVICE_URL = "http://catalog-1:8000/catalog/products"
ORDER_SERVICE_URL = "http://order-service:8000/orders/orders"


@strawberry.type(description="Товар из каталога")
class Product:
    id: strawberry.ID
    name: str
    price: float
    description: Optional[str] = None


@strawberry.type(description="Позиция в заказе")
class OrderItem:
    product: Product
    quantity: int


@strawberry.type(description="Заказ пользователя")
class Order:
    id: strawberry.ID
    userId: strawberry.ID
    createdAt: str
    items: List[OrderItem]


#  DataLoader 

def make_product_loader(client: httpx.AsyncClient) -> DataLoader:
    """
    DataLoader батчит все .load()/.load_many() за один тик event loop
    и вызывает load_fn один раз со списком ключей.
    Внутри — параллельные HTTP-запросы через asyncio.gather.
    """
    async def load_fn(ids: List[int]) -> List[Optional[Product]]:
        async def fetch(pid: int) -> Optional[Product]:
            try:
                resp = await client.get(f"{CATALOG_SERVICE_URL}/{pid}")
            except httpx.HTTPError:
                return None
            if resp.status_code != 200:
                return None
            data = resp.json()
            return Product(
                id=str(data["id"]),
                name=data["name"],
                price=float(data["price"]),
                description=data.get("description"),
            )

        return await asyncio.gather(*(fetch(pid) for pid in ids))

    return DataLoader(load_fn=load_fn)


# Резолверы

@strawberry.type(description="Корневые запросы GraphQL Gateway")
class Query:
    @strawberry.field(
        description="Все заказы пользователя с деталями товаров"
    )
    async def orders_by_user_id(
        self,
        info: Info,
        user_id: strawberry.ID,
    ) -> List[Order]:
        client: httpx.AsyncClient = info.context["client"]
        loader: DataLoader = info.context["product_loader"]

        # Заказы пользователя
        try:
            resp = await client.get(ORDER_SERVICE_URL, params={"userId": user_id})
        except httpx.HTTPError:
            return []

        if resp.status_code != 200:
            return []

        orders_data = resp.json()
        if not isinstance(orders_data, list):
            return []

        # Уникальные productId из всех заказов
        all_ids = sorted({
            item["productId"]
            for order in orders_data
            for item in order.get("items", [])
        })

        # Батч-загрузка товаров (один вызов DataLoader)
        product_map: dict = {}
        if all_ids:
            products = await loader.load_many(all_ids)
            product_map = dict(zip(all_ids, products))

        # Сборка ответа
        result: List[Order] = []
        for order in orders_data:
            order_items: List[OrderItem] = []
            for item in order.get("items", []):
                product = product_map.get(item["productId"])
                if product is not None:
                    order_items.append(OrderItem(
                        product=product,
                        quantity=item["quantity"],
                    ))
            result.append(Order(
                id=str(order["id"]),
                userId=str(order["userId"]),
                createdAt=order["createdAt"],
                items=order_items,
            ))
        return result


schema = strawberry.Schema(query=Query)


#FastAPI + lifespan

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Один общий AsyncClient на всё приложение пул соединений
    app.state.http_client = httpx.AsyncClient(timeout=5.0)
    yield
    await app.state.http_client.aclose()


app = FastAPI(
    title="GraphQL Gateway",
    description="Шлюз для агрегации данных из Order и Catalog сервисов",
    version="1.0.0",
    lifespan=lifespan,
)


async def get_context(request: Request) -> dict:
    """Контекст создаётся на каждый GraphQL-запрос.
    DataLoader обязательно должен быть новым на запрос — иначе кэш
    будет «протухать» между разными клиентами."""
    client: httpx.AsyncClient = request.app.state.http_client
    return {
        "client": client,
        "product_loader": make_product_loader(client),
    }


graphql_app = GraphQLRouter(
    schema,
    context_getter=get_context,
    graphql_ide="apollo-sandbox",
)
app.include_router(graphql_app, prefix="/graphql")

INSTANCE_ID = os.environ.get("INSTANCE_NAME", "graphql-gateway-1")
CONSUL_URL = "http://consul:8500"

def register_to_consul():
    payload = {
        "Name": "graphql-gateway",
        "ID": INSTANCE_ID,
        "Address": "graphql-gateway",
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