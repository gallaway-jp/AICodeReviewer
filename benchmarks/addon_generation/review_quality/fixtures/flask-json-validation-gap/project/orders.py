from flask import Flask, request

app = Flask(__name__)


@app.post("/orders")
def create_order():
    payload = request.get_json() or {}
    return {
        "sku": payload["sku"],
        "quantity": int(payload["quantity"]),
        "expedite": bool(payload.get("expedite")),
    }, 201