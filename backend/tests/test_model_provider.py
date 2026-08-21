from app.agents.model_provider import GroqBuyerModel


def test_convert_tools_to_groq_format():
    tools = [
        {
            "name": "search_products",
            "description": "Search products.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string"
                    }
                },
                "required": [],
            },
        }
    ]

    converted = (
        GroqBuyerModel._convert_tools(
            tools
        )
    )

    assert len(converted) == 1

    tool = converted[0]

    assert tool["type"] == "function"
    assert tool["function"]["name"] == "search_products"
    assert (
        tool["function"]["description"]
        == "Search products."
    )
    assert (
        tool["function"]["parameters"]["type"]
        == "object"
    )


def test_parse_json_tool_arguments():
    arguments = (
        '{"query":"running shoes","max_price":5000}'
    )

    parsed = (
        GroqBuyerModel._parse_arguments(
            arguments
        )
    )

    assert parsed["query"] == "running shoes"
    assert parsed["max_price"] == 5000


def test_parse_dict_tool_arguments():
    arguments = {
        "query": "running shoes",
        "max_price": 5000,
    }

    parsed = (
        GroqBuyerModel._parse_arguments(
            arguments
        )
    )

    assert parsed == arguments


def test_parse_empty_tool_arguments():
    parsed = (
        GroqBuyerModel._parse_arguments(
            ""
        )
    )

    assert parsed == {}


def test_convert_tool_result_message():
    messages = [
        {
            "role": "tool",
            "type": "tool_result",
            "tool_name": "search_products",
            "tool_call_id": "call_123",
            "content": "Found 3 products.",
        }
    ]

    converted = (
        GroqBuyerModel._convert_messages(
            messages
        )
    )

    assert len(converted) == 1

    message = converted[0]

    assert message["role"] == "tool"
    assert message["tool_call_id"] == "call_123"
    assert message["name"] == "search_products"
    assert message["content"] == "Found 3 products."


def test_convert_assistant_tool_call_message():
    messages = [
        {
            "role": "assistant",
            "type": "tool_call",
            "tool_name": "search_products",
            "tool_call_id": "call_123",
            "arguments": {
                "query": "running shoes",
                "max_price": 5000,
            },
            "content": None,
        }
    ]

    converted = (
        GroqBuyerModel._convert_messages(
            messages
        )
    )

    assert len(converted) == 1

    message = converted[0]

    assert message["role"] == "assistant"
    assert message["content"] is None
    assert len(message["tool_calls"]) == 1

    tool_call = message["tool_calls"][0]

    assert tool_call["id"] == "call_123"
    assert tool_call["type"] == "function"
    assert (
        tool_call["function"]["name"]
        == "search_products"
    )