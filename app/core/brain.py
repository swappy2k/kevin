from app.core.config import config
from app.core.memory import MemorySystem
from app.core.personality import SYSTEM_PROMPT


class KevinBrain:

    def __init__(self):

        self.memory = MemorySystem(
            config.DATA_FILE
        )

        self.name = config.KEVIN_NAME

        self.owner = (
            self.memory.get_owner()
            or config.OWNER_NAME
        )

    def get_system_prompt(self):

        memories = self.memory.get_memories()

        memory_text = "\n".join(
            f"- {memory.get('text', '')}"
            for memory in memories[-10:]
        )

        return f"""
{SYSTEM_PROMPT}

OWNER:
{self.owner}

CURRENT MEMORY:
{memory_text or "No memories stored."}
"""

    def remember(self, text: str):

        self.memory.remember(text)

        return "Saved to memory."

    def recall(self):

        memories = self.memory.get_memories()

        if not memories:
            return "I don't have any saved memories yet."

        return "\n".join(
            f"{index}. {memory.get('text', '')}"
            for index, memory in enumerate(
                memories,
                start=1,
            )
        )

    def status(self):

        tasks = self.memory.get_tasks()

        open_tasks = [
            task
            for task in tasks
            if not task.get("complete", False)
        ]

        memories = self.memory.get_memories()

        return {
            "owner": self.owner,
            "open_tasks": len(open_tasks),
            "memories": len(memories),
        }