from app.agents.model import MockBuyerModel


def test_mock_model_requests_product_search():
    model = MockBuyerModel()

    response = model.invoke(
        messages=[
            {
                "role": "user",
                "content": "I need running shoes",
            }
        ],
        tools=[],
    )

    assert response.has_tool_calls is True
    assert len(response.tool_calls) == 1

    tool_call = response.tool_calls[0]

    assert tool_call.tool_name == "search_products"
    assert tool_call.arguments["query"] == "running shoes"


def test_mock_model_returns_text_when_no_tool_is_needed():
    model = MockBuyerModel()

    response = model.invoke(
        messages=[
            {
                "role": "user",
                "content": "Hello",
            }
        ],
        tools=[],
    )

    assert response.has_tool_calls is False
    assert response.content is not None