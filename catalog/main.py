import os

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, Session, SQLModel, create_engine, select


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./catalog.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
app = FastAPI(title="Catalog Service", version="1.0.0")


class Product(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    price_cents: int


class ProductCreate(BaseModel):
    name: str = PydanticField(min_length=1, max_length=100)
    price_cents: int = PydanticField(gt=0)


SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


@app.post("/products", status_code=201)
def create_product(product_data: ProductCreate, session: Session = Depends(get_session)):
    product = Product(name=product_data.name, price_cents=product_data.price_cents)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


@app.get("/products")
def list_products(session: Session = Depends(get_session)):
    return session.exec(select(Product)).all()


@app.get("/products/{product_id}")
def get_product(product_id: int, session: Session = Depends(get_session)):
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    return product


@app.get("/health")
def health():
    return {"status": "ok", "service": "catalog"}

