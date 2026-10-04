"""
Unit & Integration Tests for Krīya V1 (Tool Execution Layer) & Smṛti V2 (Persistent Memory).
Verifies:
- Timezone resolution and get_current_time(location)
- get_current_date()
- Safe AST calculator (847 * 392 = 332024, division by zero, invalid input)
- Smṛti V2 persistent memory operations (save, update, retrieve, delete/forget, list, context generation)
- Krīya dispatcher provider-independent schemas (OpenAI and Gemini formats)
- Asynchronous tool execution through Krīya dispatcher
"""

import unittest
import asyncio
from app.services.kriya import (
    kriya_dispatcher,
    get_current_time,
    get_current_date,
    calculator,
    save_memory,
    retrieve_memory,
    delete_memory,
    list_memories,
    web_search,
    resolve_timezone,
)
from app.services.smriti import smriti_service


class TestKriyaTools(unittest.TestCase):
    def test_01_timezones(self):
        self.assertEqual(resolve_timezone("New York"), "America/New_York")
        self.assertEqual(resolve_timezone("India"), "Asia/Kolkata")
        self.assertEqual(resolve_timezone("Delhi"), "Asia/Kolkata")
        self.assertEqual(resolve_timezone("London"), "Europe/London")
        self.assertEqual(resolve_timezone("Tokyo"), "Asia/Tokyo")

    def test_02_get_current_time(self):
        ny = get_current_time("New York")
        self.assertEqual(ny["location"], "New York")
        self.assertEqual(ny["resolved_timezone"], "America/New_York")
        self.assertIn("current_time", ny)
        self.assertIn("current_date", ny)

        india = get_current_time("India")
        self.assertEqual(india["location"], "India")
        self.assertEqual(india["resolved_timezone"], "Asia/Kolkata")
        self.assertIn("IST", india["timezone_abbreviation"])

    def test_03_get_current_date(self):
        date_res = get_current_date("UTC")
        self.assertIn("current_date", date_res)
        self.assertIn("iso_date", date_res)
        self.assertIn("day_of_week", date_res)
        self.assertIsInstance(date_res["year"], int)

    def test_04_calculator_exact(self):
        # Specific test required by user prompt: 847 * 392
        calc_res = calculator("847 * 392")
        self.assertEqual(calc_res["status"], "success")
        self.assertEqual(calc_res["result"], 332024)

    def test_05_calculator_advanced_and_safe(self):
        # Addition, subtraction, parenthesis, power
        r1 = calculator("(10 + 5) * 4 / 2")
        self.assertEqual(r1["result"], 30)

        r2 = calculator("2 ** 10")
        self.assertEqual(r2["result"], 1024)

        r3 = calculator("sqrt(144) + 10")
        self.assertEqual(r3["result"], 22)

        # Division by zero safety
        r4 = calculator("100 / 0")
        self.assertEqual(r4["status"], "error")
        self.assertIn("Division by zero", r4["error"])

        # Code injection prevention safety
        r5 = calculator("__import__('os').system('ls')")
        self.assertEqual(r5["status"], "error")


class TestSmritiV2PersistentMemory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.db.database import init_db
        init_db()

    def setUp(self):
        # Clean up any test keys
        smriti_service.delete_memory("test_name")
        smriti_service.delete_memory("test_fav_color")

    def tearDown(self):
        smriti_service.delete_memory("test_name")
        smriti_service.delete_memory("test_fav_color")

    def test_01_save_and_retrieve_memory(self):
        # 1. Save
        res = smriti_service.save_memory("test_name", "Pratyush", "profile")
        self.assertEqual(res["status"], "saved")
        self.assertEqual(res["message"], "Saved to Smṛti.")
        self.assertEqual(res["key"], "test_name")
        self.assertEqual(res["value"], "Pratyush")

        # 2. Retrieve
        ret = smriti_service.retrieve_memory("test_name")
        self.assertTrue(ret["found"])
        self.assertEqual(ret["value"], "Pratyush")

    def test_02_update_memory(self):
        smriti_service.save_memory("test_name", "Pratyush", "profile")
        # Update existing
        update_res = smriti_service.save_memory("test_name", "Pratyush J.", "profile")
        self.assertEqual(update_res["status"], "updated")
        self.assertEqual(update_res["message"], "Updated in Smṛti.")

        ret = smriti_service.retrieve_memory("test_name")
        self.assertEqual(ret["value"], "Pratyush J.")

    def test_03_delete_and_forget_memory(self):
        smriti_service.save_memory("test_name", "Pratyush", "profile")
        # Delete
        del_res = smriti_service.delete_memory("test_name")
        self.assertEqual(del_res["status"], "deleted")
        self.assertEqual(del_res["message"], "Deleted from Smṛti.")

        # Verify not found after deletion
        ret = smriti_service.retrieve_memory("test_name")
        self.assertFalse(ret["found"])

    def test_04_relevant_memories_context_generation(self):
        smriti_service.save_memory("test_fav_color", "Deep Indigo", "preference")
        ctx = smriti_service.get_relevant_memories_context(query="fav color")
        self.assertIn("test_fav_color", ctx)
        self.assertIn("Deep Indigo", ctx)


class TestKriyaDispatcher(unittest.TestCase):
    def test_01_schemas_formats(self):
        # OpenAI/Groq format
        openai_schemas = kriya_dispatcher.get_schemas("openai")
        self.assertGreaterEqual(len(openai_schemas), 7)
        names = [s["function"]["name"] for s in openai_schemas]
        self.assertIn("get_current_time", names)
        self.assertIn("get_current_date", names)
        self.assertIn("calculator", names)
        self.assertIn("save_memory", names)
        self.assertIn("retrieve_memory", names)
        self.assertIn("delete_memory", names)
        self.assertIn("list_memories", names)
        self.assertIn("web_search", names)

        # Gemini format
        gemini_schemas = kriya_dispatcher.get_schemas("gemini")
        self.assertEqual(len(gemini_schemas), len(openai_schemas))
        self.assertIn("name", gemini_schemas[0])

    def test_02_async_dispatcher_execution(self):
        # Test calculator via dispatcher
        calc_result = asyncio.run(
            kriya_dispatcher.execute_tool("calculator", {"expression": "847 * 392"})
        )
        self.assertEqual(calc_result["result"], 332024)

        # Test web_search via dispatcher
        search_result = asyncio.run(
            kriya_dispatcher.execute_tool("web_search", {"query": "Groq documentation", "max_results": 2})
        )
        self.assertEqual(search_result["status"], "success")
        self.assertGreaterEqual(search_result["count"], 1)
        self.assertTrue(search_result["results"][0]["url"].startswith("http"))

        # Test time via dispatcher
        ny_result = asyncio.run(
            kriya_dispatcher.execute_tool("get_current_time", {"location": "New York"})
        )
        self.assertEqual(ny_result["resolved_timezone"], "America/New_York")

        # Test memory via dispatcher
        save_res = asyncio.run(
            kriya_dispatcher.execute_tool(
                "save_memory",
                {"key": "test_agent", "value": "NARAD", "category": "system"}
            )
        )
        self.assertIn("Saved to Smṛti", save_res["message"])

        # Test list_memories via dispatcher with various parameter formats
        list_res1 = asyncio.run(
            kriya_dispatcher.execute_tool("list_memories", {})
        )
        self.assertIn("memories", list_res1)
        self.assertIsInstance(list_res1["memories"], list)

        # Test list_memories with category: None (simulating Groq arguments: {"category": null})
        list_res2 = asyncio.run(
            kriya_dispatcher.execute_tool("list_memories", {"category": None})
        )
        self.assertIn("memories", list_res2)
        self.assertEqual(len(list_res2["memories"]), len(list_res1["memories"]))

        # Test list_memories with string literal "null"
        list_res3 = asyncio.run(
            kriya_dispatcher.execute_tool("list_memories", {"category": "null"})
        )
        self.assertEqual(len(list_res3["memories"]), len(list_res1["memories"]))

        # Test direct list_memories function
        self.assertEqual(len(list_memories()["memories"]), len(list_res1["memories"]))
        self.assertEqual(len(list_memories(category=None)["memories"]), len(list_res1["memories"]))
        self.assertEqual(len(list_memories(category="null")["memories"]), len(list_res1["memories"]))

        del_res = asyncio.run(
            kriya_dispatcher.execute_tool("delete_memory", {"key": "test_agent"})
        )
        self.assertEqual(del_res["status"], "deleted")


if __name__ == "__main__":
    unittest.main()
