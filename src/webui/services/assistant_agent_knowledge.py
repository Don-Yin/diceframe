"""Bounded, optional documentation lookup for the application agent."""

import inspect


def documentation_tool(lookup):
    from src.webui.services.assistant_agent import AgentTool

    async def search(args, owner):
        result = lookup(args["question"], args["language"])
        return await result if inspect.isawaitable(result) else result

    return AgentTool(
        "search_documentation",
        "Search this installed version's bundled help for usage or deployment questions. "
        "Use live application tools for actions, IDs and current state; documentation does not grant capabilities.",
        {"type": "object", "properties": {
            "question": {"type": "string", "minLength": 1, "maxLength": 1000},
            "language": {"type": "string", "enum": ["en", "zh-CN"]},
        }, "required": ["question", "language"], "additionalProperties": False},
        search,
    )
