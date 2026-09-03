import tempfile
import unittest
from pathlib import Path

from app.ai.main import KevinState, Memory, StateStore, Task, command, kevin_instructions, personal_reply, state_summary


class StateStoreTests(unittest.TestCase):
    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            original = KevinState(
                owner="Kevin",
                tasks=[Task("Ship the prototype", "Friday")],
                memories=[Memory("Prefers concise answers")],
            )
            store.save(original)
            loaded = store.load()

        self.assertEqual(loaded.owner, "Kevin")
        self.assertEqual(loaded.tasks[0].text, "Ship the prototype")
        self.assertEqual(loaded.memories[0].text, "Prefers concise answers")

    def test_summary_does_not_include_completed_tasks(self):
        state = KevinState(tasks=[Task("Open", complete=False), Task("Done", complete=True)])
        summary = state_summary(state)
        self.assertIn("Open", summary)
        self.assertNotIn("Done", summary)

    def test_kevin_instructions_include_persona_and_private_context(self):
        instructions = kevin_instructions(KevinState(owner="Swappy", memories=[Memory("Likes tea")]))
        self.assertIn("real person texting a close friend", instructions)
        self.assertIn("Swappy", instructions)
        self.assertIn("Likes tea", instructions)
        self.assertIn("My owner is Swappy.", instructions)

    def test_personal_relationship_replies(self):
        self.assertEqual(personal_reply("Who is Hetvi?"), "Hetvi is my mother.")
        self.assertEqual(personal_reply("tell me who is hetvi"), "Hetvi is my mother.")
        self.assertEqual(personal_reply("hetvi ko janta hai kya?"), "Hetvi is my mother.")
        self.assertEqual(personal_reply("who is ur mother?"), "Hetvi is my mother.")
        self.assertEqual(personal_reply("Who is ur mother Kevin?"), "Hetvi is my mother.")
        self.assertEqual(personal_reply("who i'm ur"), "You are my owner.")
        self.assertEqual(personal_reply("who im?"), "You are my owner.")

    def test_task_commands_use_one_based_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            state = KevinState()
            command(state, store, "/task Send proposal | tomorrow")
            command(state, store, "/done 0")
            self.assertFalse(state.tasks[0].complete)
            command(state, store, "/done 1")
            self.assertTrue(state.tasks[0].complete)


if __name__ == "__main__":
    unittest.main()
