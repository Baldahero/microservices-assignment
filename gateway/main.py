import os

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


AUTH_URL = os.getenv("AUTH_URL", "http://127.0.0.1:8001")
CATALOG_URL = os.getenv("CATALOG_URL", "http://127.0.0.1:8002")
ORDER_URL = os.getenv("ORDER_URL", "http://127.0.0.1:8003")

app = FastAPI(
    title="Online Store API Gateway",
    description="One public API for the Auth, Catalog and Order microservices.",
    version="1.0.0",
)


class UserCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=4, max_length=128)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price_cents: int = Field(gt=0)


class OrderCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000)


def auth_header(authorization: str | None) -> dict[str, str]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid authorization header")
    return {"Authorization": authorization}


async def request_service(method: str, url: str, **kwargs):
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Required microservice is unavailable") from exc

    try:
        content = response.json()
    except ValueError:
        content = {"detail": response.text or "Microservice returned an invalid response"}
    return JSONResponse(status_code=response.status_code, content=content)


async def current_user(authorization: str | None = Header(default=None)) -> str:
    headers = auth_header(authorization)
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.get(f"{AUTH_URL}/verify", headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Auth service is unavailable") from exc

    if response.status_code != 200:
        detail = response.json().get("detail", "Authentication failed")
        raise HTTPException(response.status_code, detail)
    return response.json()["username"]


@app.post("/auth/register")
async def register(credentials: UserCredentials):
    return await request_service("POST", f"{AUTH_URL}/register", json=credentials.model_dump())


@app.post("/auth/token")
async def login(credentials: UserCredentials):
    return await request_service("POST", f"{AUTH_URL}/token", json=credentials.model_dump())


@app.post("/auth/logout")
async def logout(authorization: str | None = Header(default=None)):
    return await request_service("POST", f"{AUTH_URL}/logout", headers=auth_header(authorization))


@app.post("/catalog/products")
async def create_product(product: ProductCreate, user: str = Depends(current_user)):
    return await request_service("POST", f"{CATALOG_URL}/products", json=product.model_dump())


@app.get("/catalog/products")
async def list_products(user: str = Depends(current_user)):
    return await request_service("GET", f"{CATALOG_URL}/products")


@app.get("/catalog/products/{product_id}")
async def get_product(product_id: int, user: str = Depends(current_user)):
    return await request_service("GET", f"{CATALOG_URL}/products/{product_id}")


@app.post("/orders")
async def create_order(order: OrderCreate, user: str = Depends(current_user)):
    return await request_service(
        "POST",
        f"{ORDER_URL}/orders",
        json=order.model_dump(),
        headers={"X-User": user},
    )


@app.get("/orders")
async def list_orders(user: str = Depends(current_user)):
    return await request_service("GET", f"{ORDER_URL}/orders", headers={"X-User": user})


@app.get("/health")
def health():
    return {"status": "ok", "service": "gateway"}
