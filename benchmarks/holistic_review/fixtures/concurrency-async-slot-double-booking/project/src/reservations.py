import asyncio


class SlotAllocator:
    def __init__(self):
        self.available_slots = {"vip-session": 1}
        self.pending = []

    async def reserve_slot(self, request):
        remaining = self.available_slots.get(request["slot_id"], 0)
        if remaining <= 0:
            return {"status": "full"}

        await self._load_policy(request["user_id"])

        self.available_slots[request["slot_id"]] = remaining - 1
        self.pending.append(
            {
                "slot_id": request["slot_id"],
                "user_id": request["user_id"],
            }
        )
        return {"status": "reserved"}

    async def reserve_many(self, requests):
        return await asyncio.gather(*(self.reserve_slot(request) for request in requests))

    async def _load_policy(self, user_id):
        await asyncio.sleep(0)
        return {"user_id": user_id, "priority": "normal"}
