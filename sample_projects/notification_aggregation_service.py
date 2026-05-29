import asyncio
from fastapi import FastAPI


app = FastAPI()

PROVIDERS = ["sms", "email", "push"]
FAILED_MESSAGES = []


async def send_to_provider(provider: str, user_id: str, message: str):
    await asyncio.sleep(0.1)
    if provider == "sms" and "urgent" in message:
        raise RuntimeError("provider rate limited")
    return {"provider": provider, "status": "sent"}


@app.post("/notifications/fanout")
async def fanout_notification(payload: dict):
    user_ids = payload.get("user_ids", [])
    message = payload["message"]
    results = []

    for user_id in user_ids:
        for provider in PROVIDERS:
            try:
                result = await send_to_provider(provider, user_id, message)
                results.append(result)
            except Exception:
                FAILED_MESSAGES.append(
                    {"user_id": user_id, "provider": provider, "message": message}
                )

    return {
        "requested": len(user_ids) * len(PROVIDERS),
        "sent": len(results),
        "failed": len(FAILED_MESSAGES),
    }


@app.post("/notifications/retry")
async def retry_failed_notifications():
    for failed in FAILED_MESSAGES:
        await send_to_provider(
            failed["provider"],
            failed["user_id"],
            failed["message"],
        )
    FAILED_MESSAGES.clear()
    return {"status": "retried"}
