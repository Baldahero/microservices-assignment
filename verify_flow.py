"""End-to-end check. Run while start_all.py is active."""

import secrets

import httpx


BASE_URL = "http://127.0.0.1:8000"


def expect(response: httpx.Response, status_code: int):
    if response.status_code != status_code:
        raise RuntimeError(f"{response.request.method} {response.url}: {response.status_code} {response.text}")
    return response.json()


def main():
    username = f"student_{secrets.token_hex(3)}"
    password = "test1234"
    with httpx.Client(base_url=BASE_URL, timeout=10, trust_env=False) as client:
        expect(client.post("/auth/register", json={"username": username, "password": password}), 201)
        login = expect(client.post("/auth/token", json={"username": username, "password": password}), 200)
        headers = {"Authorization": f"Bearer {login['access_token']}"}

        product = expect(
            client.post("/catalog/products", json={"name": "Test product", "price_cents": 1299}, headers=headers),
            201,
        )
        expect(client.get("/catalog/products", headers=headers), 200)
        order = expect(
            client.post("/orders", json={"product_id": product["id"], "quantity": 2}, headers=headers),
            201,
        )
        orders = expect(client.get("/orders", headers=headers), 200)
        assert order["total_cents"] == 2598
        assert any(item["id"] == order["id"] for item in orders)

        expect(client.post("/auth/logout", headers=headers), 200)
        expect(client.get("/catalog/products", headers=headers), 401)
    print("SUCCESS: register, login, products, orders and logout all work.")


if __name__ == "__main__":
    main()
