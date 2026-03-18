"""Example: Random agent that makes random decisions."""

import asyncio
import random

from werewolf_sdk import AgentBase, WerewolfClient


class RandomAgent(AgentBase):
    """An agent that makes random choices - good for testing."""

    async def on_game_start(self, data: dict) -> None:
        print(f"Game started! I am {data['your_role']} at seat {data['your_seat']}")

    async def on_night_action(self, data: dict) -> dict:
        targets = data.get("available_targets", [])
        action_type = data.get("action_type", "skip")

        if action_type == "kill" and targets:
            return {"action_type": "kill", "target_seat": random.choice(targets)}
        elif action_type == "investigate" and targets:
            return {"action_type": "investigate", "target_seat": random.choice(targets)}
        elif action_type == "heal_or_poison":
            if data.get("heal_remaining", 0) > 0 and random.random() < 0.5:
                return {"action_type": "heal"}
            elif data.get("poison_remaining", 0) > 0 and random.random() < 0.3:
                poison_targets = data.get("available_poison_targets", [])
                if poison_targets:
                    return {
                        "action_type": "poison",
                        "target_seat": random.choice(poison_targets),
                    }
            return {"action_type": "skip"}
        return {"action_type": "skip"}

    async def on_speech_request(self, data: dict) -> dict:
        phrases = [
            "我觉得有人很可疑...",
            "昨晚的情况来看，我怀疑某些人",
            "我是好人，请相信我",
            "大家要注意投票",
            "我观察到一些异常行为",
        ]
        return {"content": random.choice(phrases)}

    async def on_vote_request(self, data: dict) -> dict:
        candidates = data.get("candidates", [])
        my_seat = data.get("your_seat")
        options = [s for s in candidates if s != my_seat] or [0]
        return {"target_seat": random.choice(options)}


async def main():
    async with WerewolfClient("http://localhost:8000") as client:
        # Register
        agent_data = await client.register_agent("RandomBot")
        api_key = agent_data["api_key"]
        print(f"Registered: {agent_data['name']} (key: {api_key[:20]}...)")

        # Find or create room
        rooms = await client.list_rooms(status="waiting")
        if rooms["rooms"]:
            room_id = rooms["rooms"][0]["id"]
        else:
            room = await client.create_room("Test Game", player_count=8)
            room_id = room["id"]

        # Join room
        join_data = await client.join_room(room_id)
        print(f"Joined room {room_id}, seat {join_data['seat']}")

        # Play
        agent = RandomAgent(api_key=api_key)
        await agent.connect_and_play(room_id)


if __name__ == "__main__":
    asyncio.run(main())
