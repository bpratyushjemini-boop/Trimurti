"""
Unit & Integration Tests for NARAD Local Tool Execution & Dispatching Subsystem.
Verifies timezone resolution, tool execution, argument parsing, error recovery,
and GroqProvider message formatting and tool loop handling.
"""

import unittest
import asyncio
from typing import Dict, Any

from app.services.tools import (
    resolve_timezone,
    get_current_time,
    ToolDispatcher,
    GET_CURRENT_TIME_SCHEMA,
    tool_dispatcher,
)
from app.providers.groq import GroqProvider


class TestNaradToolDispatcher(unittest.TestCase):
    def setUp(self):
        self.dispatcher = ToolDispatcher()

    def test_01_timezone_resolution(self):
        """Verify human location strings resolve to appropriate IANA timezones."""
        self.assertEqual(resolve_timezone("New York"), "America/New_York")
        self.assertEqual(resolve_timezone("NYC"), "America/New_York")
        self.assertEqual(resolve_timezone("India"), "Asia/Kolkata")
        self.assertEqual(resolve_timezone("Delhi"), "Asia/Kolkata")
        self.assertEqual(resolve_timezone("Tokyo"), "Asia/Tokyo")
        self.assertEqual(resolve_timezone("London"), "Europe/London")
        self.assertEqual(resolve_timezone("UTC"), "UTC")

    def test_02_get_current_time_output(self):
        """Verify get_current_time returns all required structured date/time fields."""
        ny_time = get_current_time("New York")
        self.assertEqual(ny_time["location"], "New York")
        self.assertEqual(ny_time["resolved_timezone"], "America/New_York")
        self.assertIn("current_time", ny_time)
        self.assertIn("current_date", ny_time)
        self.assertIn("iso_timestamp", ny_time)

        india_time = get_current_time("India")
        self.assertEqual(india_time["resolved_timezone"], "Asia/Kolkata")
        self.assertIn("IST", india_time["timezone_abbreviation"])

    def test_03_execute_tool_success(self):
        """Verify ToolDispatcher executes registered tool synchronously and asynchronously."""
        result = asyncio.run(self.dispatcher.execute_tool("get_current_time", {"location": "New York"}))
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("location"), "New York")
        self.assertEqual(result.get("resolved_timezone"), "America/New_York")

    def test_04_execute_unknown_tool(self):
        """Verify executing an unrecognized tool returns an error dict rather than raising an unhandled exception."""
        result = asyncio.run(self.dispatcher.execute_tool("unknown_tool_xyz", {}))
        self.assertIn("error", result)
        self.assertIn("unknown_tool_xyz", result["error"])

    def test_05_execute_failing_tool(self):
        """Verify tool execution exceptions are caught and returned gracefully as error payloads."""
        def faulty_func(**kwargs):
            raise ValueError("Intentional tool failure for test")

        self.dispatcher.register_tool(
            name="faulty_tool",
            func=faulty_func,
            schema={"type": "function", "function": {"name": "faulty_tool"}}
        )

        result = asyncio.run(self.dispatcher.execute_tool("faulty_tool", {}))
        self.assertIn("error", result)
        self.assertIn("Intentional tool failure", result["error"])


class TestGroqProviderToolFormatting(unittest.TestCase):
    def setUp(self):
        self.provider = GroqProvider()

    def test_01_format_messages_standard(self):
        """Verify conversion of standard user and assistant messages."""
        input_msgs = [
            {"role": "user", "content": "What is the time?"},
            {"role": "assistant", "content": "It is 4:00 PM."}
        ]
        formatted = self.provider._format_messages_for_groq(input_msgs)
        self.assertEqual(len(formatted), 2)
        self.assertEqual(formatted[0]["role"], "user")
        self.assertEqual(formatted[0]["content"], "What is the time?")
        self.assertEqual(formatted[1]["role"], "assistant")
        self.assertEqual(formatted[1]["content"], "It is 4:00 PM.")

    def test_02_format_messages_with_tool_calls(self):
        """Verify assistant messages with tool_calls and tool result messages are formatted correctly."""
        input_msgs = [
            {"role": "user", "content": "What is the time in New York?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {"name": "get_current_time", "arguments": "{\"location\":\"New York\"}"}
                    }
                ]
            },
            {
                "role": "tool",
                "tool_call_id": "call_123",
                "name": "get_current_time",
                "content": "{\"current_time\": \"4:15 PM\"}"
            }
        ]
        formatted = self.provider._format_messages_for_groq(input_msgs)
        self.assertEqual(len(formatted), 3)

        # Assistant turn
        self.assertEqual(formatted[1]["role"], "assistant")
        self.assertIsNone(formatted[1]["content"])
        self.assertEqual(formatted[1]["tool_calls"][0]["id"], "call_123")

        # Tool turn
        self.assertEqual(formatted[2]["role"], "tool")
        self.assertEqual(formatted[2]["tool_call_id"], "call_123")
        self.assertEqual(formatted[2]["name"], "get_current_time")
        self.assertIn("4:15 PM", formatted[2]["content"])


if __name__ == "__main__":
    unittest.main()
