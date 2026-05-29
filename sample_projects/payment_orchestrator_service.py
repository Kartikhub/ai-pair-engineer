import asyncio
from fastapi import FastAPI
import httpx


app = FastAPI()

BOOKINGS = {}
PAYMENTS = {}


@app.post("/payments/confirm")
async def confirm_payment(payload: dict):
    booking_id = payload["booking_id"]
    amount = payload["amount"]

    if booking_id in PAYMENTS:
        return PAYMENTS[booking_id]

    async with httpx.AsyncClient() as client:
        payment_response = await client.post(
            "https://payments.example.com/charge",
            json={"booking_id": booking_id, "amount": amount},
        )

        if payment_response.status_code >= 500:
            await asyncio.sleep(1)
            payment_response = await client.post(
                "https://payments.example.com/charge",
                json={"booking_id": booking_id, "amount": amount},
            )

        booking_response = await client.post(
            "https://bookings.example.com/confirm",
            json={"booking_id": booking_id},
        )

    PAYMENTS[booking_id] = {
        "booking_id": booking_id,
        "payment_status": payment_response.json()["status"],
        "booking_status": booking_response.json()["status"],
    }
    BOOKINGS[booking_id] = "confirmed"
    return PAYMENTS[booking_id]


@app.get("/payments/{booking_id}")
async def get_payment(booking_id: str):
    return PAYMENTS.get(booking_id, {"status": "unknown"})
