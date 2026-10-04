"""
NARAD Tool Execution & Dispatching Subsystem.
Provides backward-compatible facades delegating directly to Krīya V1.
"""

import logging
from typing import Dict, Any, List, Optional

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
    LOCATION_TIMEZONE_MAP,
)

logger = logging.getLogger(__name__)


GET_CURRENT_TIME_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_current_time",
        "description": "Get the current time, date, day of the week, and timezone information for a given city, country, or location.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city, region, or country to check the current time for (e.g., 'New York', 'India', 'Tokyo', 'London', 'San Francisco')."
                }
            },
            "required": ["location"]
        }
    }
}


class ToolDispatcher:
    """
    Facade forwarding directly to the universal Krīya Tool Dispatcher.
    Ensures full backward-compatibility with earlier NARAD milestones.
    """

    def __init__(self):
        self._kriya = kriya_dispatcher

    def register_tool(self, name: str, func: Any, schema: Dict[str, Any]):
        from app.services.kriya import KriyaTool
        desc = schema.get("function", {}).get("description", "")
        params = schema.get("function", {}).get("parameters", {})
        self._kriya.register_tool(KriyaTool(name=name, description=desc, parameters=params, handler=func))

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return self._kriya.get_schemas(format="openai")

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        return await self._kriya.execute_tool(name, arguments)


# Global singleton Tool Dispatcher
tool_dispatcher = ToolDispatcher()

__all__ = [
    "tool_dispatcher",
    "ToolDispatcher",
    "kriya_dispatcher",
    "get_current_time",
    "get_current_date",
    "calculator",
    "save_memory",
    "retrieve_memory",
    "delete_memory",
    "list_memories",
    "web_search",
    "resolve_timezone",
    "LOCATION_TIMEZONE_MAP",
]
