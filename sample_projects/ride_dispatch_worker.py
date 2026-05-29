import asyncio
from datetime import datetime


ACTIVE_DRIVERS = {}
ALLOCATIONS = []


async def fetch_available_drivers(city_id: str):
    await asyncio.sleep(0.05)
    return ACTIVE_DRIVERS.get(city_id, [])


async def assign_driver(event: dict):
    drivers = await fetch_available_drivers(event["city_id"])

    selected_driver = None
    for driver in drivers:
        if driver["status"] == "available":
            selected_driver = driver
            break

    if not selected_driver:
        print("no drivers available")
        return None

    selected_driver["status"] = "assigned"
    allocation = {
        "ride_id": event["ride_id"],
        "driver_id": selected_driver["id"],
        "assigned_at": datetime.utcnow().isoformat(),
    }
    ALLOCATIONS.append(allocation)
    await notify_driver(selected_driver["id"], event["ride_id"])
    return allocation


async def notify_driver(driver_id: str, ride_id: str):
    await asyncio.sleep(0.2)
    print("notified", driver_id, ride_id)


async def process_events(events: list[dict]):
    tasks = []
    for event in events:
        tasks.append(assign_driver(event))
    return await asyncio.gather(*tasks)
