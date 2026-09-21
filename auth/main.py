import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, Session, SQLModel, create_engine, select


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./auth.db")
SECRET = os.getenv("JWT_SECRET", "devsecret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
app = FastAPI(title="Auth Service", version="1.0.0")


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str


class RevokedToken(SQLModel, table=True):
    jti: str = Field(primary_key=True)
    revoked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserCredentials(BaseModel):
    username: str = PydanticField(min_length=3, max_length=50)
    password: str = PydanticField(min_length=4, max_length=128)


SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000)
    return f"{salt}${digest.hex()}"


def password_is_valid(password: str, stored_value: str) -> bool:
    try:
        salt, expected = stored_value.split("$", 1)
    except ValueError:
        return False
    actual = hash_password(password, salt).split("$", 1)[1]
    return secrets.compare_digest(actual, expected)


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid authorization header")
    return authorization.split(" ", 1)[1]


def decode_active_token(token: str, session: Session) -> dict:
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        username = payload.get("sub")
        jti = payload.get("jti")
        if not username or not jti:
            raise HTTPException(401, "Invalid token")
    except JWTError as exc:
        raise HTTPException(401, "Invalid or expired token") from exc

    if session.get(RevokedToken, jti):
        raise HTTPException(401, "Token revoked")
    return payload


@app.post("/register", status_code=201)
def register(credentials: UserCredentials, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.username == credentials.username)).first()
    if existing:
        raise HTTPException(400, "Username already exists")
    user = User(
        username=credentials.username,
        hashed_password=hash_password(credentials.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return {"id": user.id, "username": user.username}


@app.post("/token")
def login(credentials: UserCredentials, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == credentials.username)).first()
    if not user or not password_is_valid(credentials.password, user.hashed_password):
        raise HTTPException(401, "Invalid credentials")

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username,
        "jti": secrets.token_urlsafe(18),
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    token = jwt.encode(payload, SECRET, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/verify")
def verify(authorization: str | None = Header(default=None), session: Session = Depends(get_session)):
    payload = decode_active_token(bearer_token(authorization), session)
    return {"username": payload["sub"]}


@app.post("/logout")
def logout(authorization: str | None = Header(default=None), session: Session = Depends(get_session)):
    payload = decode_active_token(bearer_token(authorization), session)
    session.add(RevokedToken(jti=payload["jti"]))
    session.commit()
    return {"message": "Logged out successfully"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "auth"}

