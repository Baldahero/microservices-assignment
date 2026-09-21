import os

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, Session, SQLModel, create_engine, select


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./orders.db")
CATALOG_URL = os.getenv("CATALOG_URL", "http://127.0.0.1:8002")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
app = FastAPI(title="Order Service", version="1.0.0")


class Order(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True)
    product_id: int
    product_name: str
    unit_price_cents: int
    quantity: int
    total_cents: int


class OrderCreate(BaseModel):
    product_id: int = PydanticField(gt=0)
    quantity: int = PydanticField(gt=0, le=1000)


SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


def require_user(x_user: str | None = Header(default=None, alias="X-User")) -> str:
    if not x_user:
        raise HTTPException(401, "Authenticated user is required")
    return x_user


@app.post("/orders", status_code=201)
async def create_order(
    order_data: OrderCreate,
    username: str = Depends(require_user),
    session: Session = Depends(get_session),
):
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.get(f"{CATALOG_URL}/products/{order_data.product_id}")
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Catalog service is unavailable") from exc

    if response.status_code == 404:
        raise HTTPException(400, "Product not found")
    if response.is_error:
        raise HTTPException(502, "Catalog service returned an error")

    product = response.json()
    order = Order(
        username=username,
        product_id=product["id"],
        product_name=product["name"],
        unit_price_cents=product["price_cents"],
        quantity=order_data.quantity,
        total_cents=product["price_cents"] * order_data.quantity,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


@app.get("/orders")
def list_orders(
    username: str = Depends(require_user),
    session: Session = Depends(get_session),
):
    return session.exec(select(Order).where(Order.username == username)).all()


@app.get("/health")
def health():
    return {"status": "ok", "service": "orders"}
