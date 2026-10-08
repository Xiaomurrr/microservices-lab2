from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os

app = FastAPI()

INSTANCE_ID = os.environ.get("INSTANCE_NAME", "catalog-1")

products_db = {}

next_id = 1

#post
class ProductCreate(BaseModel):
    name: str
    price: float
    description: Optional[str] = None
#put
class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None
#get
@app.get("/products")
def get_products():
    return {
        "instance_id": INSTANCE_ID,
        "products": list(products_db.values())
    }

@app.post("/products")
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

@app.put("/products/{product_id}")
def update_product(product_id: int, product: ProductUpdate):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    existing_product = products_db[product_id]
    
    update_data = product.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        existing_product[key] = value

    return existing_product

@app.delete("/products/{product_id}")
def delete_product(product_id: int):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    del products_db[product_id]
    
    return {"message": "Товар удален"}