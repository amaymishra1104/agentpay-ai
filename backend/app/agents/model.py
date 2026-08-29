from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCall:
    tool_name: str
    arguments: dict[str, Any]
    tool_call_id: str = "agentpay_tool_call"


@dataclass
class ModelResponse:
    content: str | None = None
    tool_calls: list[ToolCall] | None = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class BuyerModel:
    """Provider-independent interface for the AgentPay Buyer Agent."""

    def invoke(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        raise NotImplementedError


class MockBuyerModel(BuyerModel):
    """
    Deterministic model used by the local test suite.

    The mock intentionally does not depend on the supplied tool
    definitions. Its purpose is to simulate model intent so that
    the graph can be tested without an external LLM.
    """

    def invoke(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        user_message = self._latest_user_message(messages)
        user_message_clean = user_message.strip().lower()

        # Resolve ambiguous order selection from conversation history
        latest_assistant_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("type") == "final":
                latest_assistant_content = msg.get("content", "")
                break

        is_tracking_context = "track" in latest_assistant_content
        is_inspect_context = "inspect" in latest_assistant_content or "Which order would you like" in latest_assistant_content

        if is_tracking_context or is_inspect_context:
            prev_order_ids = re.findall(r"ord_[a-zA-Z0-9]+", latest_assistant_content)
            if prev_order_ids:
                resolved_choice_order_id = None

                # Check for explicit order ID match
                explicit_match = re.search(r"ord_[a-zA-Z0-9]+", user_message_clean)
                if explicit_match:
                    resolved_choice_order_id = explicit_match.group(0)
                # Check for "first" reference
                elif any(phrase in user_message_clean for phrase in ("first one", "first order", "first option", "the first", "number one", "first")):
                    resolved_choice_order_id = prev_order_ids[0]
                # Check for "second" reference
                elif any(phrase in user_message_clean for phrase in ("second one", "second order", "second option", "the second", "number two", "second")) and len(prev_order_ids) > 1:
                    resolved_choice_order_id = prev_order_ids[1]

                if resolved_choice_order_id:
                    target_tool_name = "get_order_tracking" if is_tracking_context else "get_order"
                    if not self._has_tool_result_after_latest_user(messages, target_tool_name):
                        return ModelResponse(
                            tool_calls=[
                                ToolCall(
                                    tool_name=target_tool_name,
                                    arguments={"order_id": resolved_choice_order_id},
                                )
                            ]
                        )

        # 1. Checkout confirmation flow
        # Check if the assistant asked for confirmation in the last assistant message
        asked_confirmation = False
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("type") == "final":
                last_assistant_msg = msg.get("content", "")
                if "Would you like me to place the order?" in last_assistant_msg:
                    asked_confirmation = True
                break

        is_yes = any(word in user_message_clean for word in ("yes", "place it", "place the order", "confirm", "ok", "sure", "yep", "do it"))

        if asked_confirmation and is_yes:
            if self._has_tool_result_after_latest_user(messages, "checkout_cart"):
                tool_res = self._latest_tool_result(messages, "checkout_cart")
                order_id = tool_res.get("order_id", "ord_mock") if tool_res else "ord_mock"
                total = tool_res.get("total", 0) if tool_res else 0
                return ModelResponse(
                    content=f"Order placed successfully ✓\n\nOrder ID: {order_id}\nTotal: ₹{total}\nPayment: Mock UPI — Successful\nEstimated delivery: 3–4 days"
                )
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        tool_name="checkout_cart",
                        arguments={},
                    )
                ]
            )

        if any(phrase in user_message_clean for phrase in ("checkout", "buy everything", "place the order", "proceed to checkout", "place order")):
            if self._has_tool_result_after_latest_user(messages, "get_cart"):
                cart_res = self._latest_tool_result(messages, "get_cart")
                total = cart_res.get("total_inr", 0) if cart_res else 0
                items_count = sum(item.get("quantity", 0) for item in cart_res.get("items", [])) if cart_res else 0
                return ModelResponse(
                    content=f"Your order total is ₹{total}.\nItems: {items_count}\nShipping: Free\nPayment: Mock UPI\n\nWould you like me to place the order?"
                )
            else:
                return ModelResponse(
                    tool_calls=[
                        ToolCall(
                            tool_name="get_cart",
                            arguments={},
                        )
                    ]
                )

        # Resolve order_id from tool history if available
        def get_latest_order_id() -> str | None:
            for m in reversed(messages):
                if m.get("type") == "tool_result" or m.get("role") == "tool":
                    try:
                        content = m.get("content", "")
                        if isinstance(content, str):
                            import json
                            parsed = json.loads(content)
                        else:
                            parsed = content
                        if isinstance(parsed, dict):
                            if "order_id" in parsed:
                                return parsed["order_id"]
                            if "orders" in parsed and isinstance(parsed["orders"], list) and parsed["orders"]:
                                return parsed["orders"][0]["order_id"]
                    except Exception:
                        pass
            return None

        latest_order_id = get_latest_order_id()

        # Identify latest assistant response content
        latest_assistant_content = ""
        for m in reversed(messages):
            if m.get("role") == "assistant" or m.get("type") == "assistant":
                latest_assistant_content = str(m.get("content", "")).lower()
                break

        # 2. Order query flow (items, status, tracking, cancellation, return)
        is_tracking_query = any(phrase in user_message_clean for phrase in ("where is my", "track", "tracking", "arrive", "shipped", "delivery", "delivered"))
        is_cancel_query = any(phrase in user_message_clean for phrase in ("cancel", "cancellation"))
        is_return_query = any(phrase in user_message_clean for phrase in ("return", "refund"))
        is_items_query = any(phrase in user_message_clean for phrase in ("what did i buy", "what did i just buy", "what did i purchase", "purchased items"))
        is_status_query = any(phrase in user_message_clean for phrase in ("status of my", "order status", "my order status", "what is my order"))

        # Cancellation confirmation check
        if is_cancel_query and any(word in user_message_clean for word in ("yes", "confirm", "proceed", "cancel it")) and "cancel" in latest_assistant_content:
            if latest_order_id:
                return ModelResponse(
                    tool_calls=[ToolCall(tool_name="cancel_order", arguments={"order_id": latest_order_id})]
                )

        # Return confirmation check
        if is_return_query and any(word in user_message_clean for word in ("yes", "confirm", "proceed", "return it")) and "return" in latest_assistant_content:
            if latest_order_id:
                return ModelResponse(
                    tool_calls=[ToolCall(tool_name="request_return", arguments={"order_id": latest_order_id, "product_id": "ur_audio_001", "quantity": 1})]
                )

        if is_cancel_query:
            if self._has_tool_result_after_latest_user(messages, "cancel_order"):
                tool_res = self._latest_tool_result(messages, "cancel_order")
                if tool_res and tool_res.get("status") == "cancelled":
                    return ModelResponse(content=f"Your order {tool_res.get('order_id')} has been successfully cancelled and refunded.")
                else:
                    return ModelResponse(content="I was unable to cancel your order.")
            
            if self._has_tool_result_after_latest_user(messages, "get_order"):
                order_res = self._latest_tool_result(messages, "get_order")
                if order_res:
                    status = order_res.get("status", "placed")
                    if status in ("placed", "confirmed", "packed"):
                        return ModelResponse(content=f"Your order {order_res.get('order_id')} is currently in status '{status}' and is eligible for cancellation. Would you like me to cancel it?")
                    else:
                        return ModelResponse(content=f"Your order {order_res.get('order_id')} is in status '{status}', which is not eligible for cancellation (only placed, confirmed, or packed orders can be cancelled).")
            
            return ModelResponse(tool_calls=[ToolCall(tool_name="get_order", arguments={})])

        if is_return_query:
            if self._has_tool_result_after_latest_user(messages, "request_return"):
                tool_res = self._latest_tool_result(messages, "request_return")
                if tool_res and tool_res.get("return_id"):
                    return ModelResponse(content=f"Return request submitted successfully ✓. Return ID: {tool_res.get('return_id')}.")
                else:
                    return ModelResponse(content="I was unable to submit a return request.")

            if self._has_tool_result_after_latest_user(messages, "get_order"):
                order_res = self._latest_tool_result(messages, "get_order")
                if order_res:
                    status = order_res.get("status", "placed")
                    if status == "delivered":
                        return ModelResponse(content=f"Your order {order_res.get('order_id')} is delivered and eligible for return. Would you like me to submit a return request?")
                    else:
                        return ModelResponse(content=f"Your order {order_res.get('order_id')} is in status '{status}'. Only delivered orders can be returned.")
            
            return ModelResponse(tool_calls=[ToolCall(tool_name="get_order", arguments={})])

        if is_tracking_query:
            if self._has_tool_result_after_latest_user(messages, "get_order_tracking"):
                tool_res = self._latest_tool_result(messages, "get_order_tracking")
                if tool_res:
                    if tool_res.get("multiple_orders"):
                        orders_list = "\n".join(f"- Order ID: {o.get('order_id')} (Date: {o.get('date')[:10]}, Total: ₹{o.get('total')})" for o in tool_res.get("orders", []))
                        return ModelResponse(content=f"I found multiple orders for you. Which order would you like me to track?\n\n{orders_list}")
                    
                    status = tool_res.get("status", "placed")
                    est = tool_res.get("estimated_delivery", "")
                    num = tool_res.get("tracking_number", "")
                    carrier = tool_res.get("carrier", "")
                    return ModelResponse(content=f"Your order status is '{status}'.\n- Carrier: {carrier}\n- Tracking Number: {num}\n- Estimated Delivery: {est}")
            
            return ModelResponse(tool_calls=[ToolCall(tool_name="get_order_tracking", arguments={})])

        if is_items_query or is_status_query:
            if self._has_tool_result_after_latest_user(messages, "get_order"):
                order_res = self._latest_tool_result(messages, "get_order")
                if order_res:
                    if order_res.get("multiple_orders"):
                        orders_list = "\n".join(f"- Order ID: {o.get('order_id')} (Date: {o.get('date')[:10]}, Total: ₹{o.get('total')})" for o in order_res.get("orders", []))
                        return ModelResponse(content=f"I found multiple orders for you. Which order would you like to inspect?\n\n{orders_list}")
                    
                    order_id = order_res.get("order_id", "ord_mock")
                    status = order_res.get("status", "placed")
                    items_desc = ", ".join(f"{item.get('name')} x{item.get('quantity')}" for item in order_res.get("items", []))
                    if is_status_query:
                        return ModelResponse(content=f"Your order {order_id} is currently in status '{status}'.")
                    else:
                        return ModelResponse(content=f"You bought the following items: {items_desc}. (Order ID: {order_id})")
            
            return ModelResponse(tool_calls=[ToolCall(tool_name="get_order", arguments={})])

        # 3. Existing mock flows
        if "cart" in user_message and any(
            phrase in user_message
            for phrase in ("what", "show", "view", "see", "check")
        ):
            if self._has_tool_result_after_latest_user(messages, "get_cart"):
                return ModelResponse(content="Here is what is currently in your cart.")

            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        tool_name="get_cart",
                        arguments={},
                    )
                ]
            )

        # Comparison flow
        if any(phrase in user_message for phrase in ("compare", "which one is better", "which is better", "better option", "which product")):
            if self._has_tool_result_after_latest_user(messages, "compare_products"):
                tool_res = self._latest_tool_result(messages, "compare_products")
                if tool_res and tool_res.get("products"):
                    p_names = " and ".join(p.get("name", "") for p in tool_res["products"][:2])
                    return ModelResponse(
                        content=f"Here is a comparison between {p_names}. Both offer excellent features with top build quality."
                    )
                return ModelResponse(
                    content="I compared the matching products for you."
                )

            product_ids = self._search_product_ids(messages)[:2]
            if len(product_ids) >= 2:
                return ModelResponse(
                    tool_calls=[
                        ToolCall(
                            tool_name="compare_products",
                            arguments={"product_ids": product_ids},
                        )
                    ]
                )

        # Cheaper refinement flow
        if "cheaper" in user_message or "lower price" in user_message or "less expensive" in user_message:
            if self._has_tool_result_after_latest_user(messages, "search_products"):
                tool_res = self._latest_tool_result(messages, "search_products")
                category_name = "products"
                if tool_res and tool_res.get("items"):
                    first_item = tool_res["items"][0]
                    category_name = first_item.get("category", "products").replace("_", " ")
                return ModelResponse(
                    content=f"Here are more affordable {category_name} from our catalog."
                )

            prev_query = "running shoes"
            for m in reversed(messages):
                if m.get("type") == "tool_result" and m.get("tool_name") == "search_products":
                    content = m.get("content", "")
                    if isinstance(content, str) and "running" in content:
                        prev_query = "running"
                    break

            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        tool_name="search_products",
                        arguments={
                            "query": prev_query,
                            "max_price": 3000,
                        },
                    )
                ]
            )

        # Add or Remove cart flow
        if any(
            phrase in user_message
            for phrase in ("add ", "put ", "remove", "take ", "delete")
        ) and ("cart" in user_message or "back" in user_message or "remove" in user_message or "item" in user_message):
            if self._has_tool_result_after_latest_user(messages, "add_to_cart") or self._has_tool_result_after_latest_user(messages, "remove_from_cart"):
                return ModelResponse(
                    content="I updated your cart."
                )

            is_remove = any(w in user_message for w in ("remove", "take ", "delete"))
            product_ids = self._search_product_ids(messages)
            product_id = None

            if "second" in user_message and len(product_ids) > 1:
                product_id = product_ids[1]
            elif "first" in user_message and len(product_ids) > 0:
                product_id = product_ids[0]
            elif is_remove:
                # Find most recently added product from add_to_cart tool call or cart item in history
                for m in reversed(messages):
                    if m.get("type") == "tool_call" and m.get("tool_name") == "add_to_cart":
                        args = m.get("arguments") or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                pass
                        if isinstance(args, dict) and "product_id" in args:
                            product_id = args["product_id"]
                            break
                    if m.get("type") == "tool_result" and m.get("tool_name") in ("add_to_cart", "get_cart"):
                        content = m.get("content", "")
                        try:
                            parsed = json.loads(content) if isinstance(content, str) else content
                            if isinstance(parsed, dict) and parsed.get("items"):
                                product_id = parsed["items"][-1].get("product_id")
                                break
                        except Exception:
                            pass
                if not product_id and product_ids:
                    product_id = product_ids[0]

            # If no product_id from search, try resolving from cart items
            if not product_id:
                for m in reversed(messages):
                    if m.get("type") == "tool_result":
                        content = m.get("content", "")
                        if "items" in str(content):
                            try:
                                parsed = json.loads(content) if isinstance(content, str) else content
                                if isinstance(parsed, dict) and parsed.get("items"):
                                    product_id = parsed["items"][0].get("product_id")
                            except Exception:
                                pass
                        if product_id:
                            break

            if product_id:
                action = "remove_from_cart" if is_remove else "add_to_cart"
                arguments = {"product_id": product_id}
                if action == "add_to_cart":
                    arguments["quantity"] = 1
                return ModelResponse(
                    tool_calls=[
                        ToolCall(
                            tool_name=action,
                            arguments=arguments,
                        )
                    ]
                )

        # Identify search keywords from user message dynamically
        search_keywords = [
            "running", "shoes", "shoe", "trail", "headphones", "headphone", "earbuds", "earphones",
            "apparel", "tshirt", "shorts", "jacket", "hoodie", "tights",
            "backpack", "backpacks", "bag", "bags", "duffel", "rucksack",
            "watch", "watches", "smartwatch", "tracker",
            "equipment", "dumbbell", "pullup", "kettlebell", "rope", "bands",
            "yoga", "mat", "blocks", "wheel",
            "recovery", "massage", "ice", "acupressure",
            "cycling", "bike", "helmet", "light", "gloves",
            "electronics", "power bank", "scale", "speaker", "laptop", "laptops",
            "hydration", "bottle", "flask", "shaker",
            "sock", "socks",
            "accessories", "cap", "sunglasses", "armband", "chafe",
            "workout", "beginner", "gift", "deals", "rated", "product"
        ]
        matched_keyword = None
        for kw in search_keywords:
            if kw in user_message:
                matched_keyword = kw
                break

        # If the graph has already executed a tool, the model
        # should produce a final response rather than repeatedly
        # requesting another tool.
        if any(
            message.get("type") == "tool_result"
            for message in messages
        ):
            # If the tool was checkout_cart, handle final response here too
            if self._has_tool_result_after_latest_user(messages, "checkout_cart"):
                tool_res = self._latest_tool_result(messages, "checkout_cart")
                order_id = tool_res.get("order_id", "ord_mock") if tool_res else "ord_mock"
                total = tool_res.get("total", 0) if tool_res else 0
                return ModelResponse(
                    content=f"Order placed successfully ✓\n\nOrder ID: {order_id}\nTotal: ₹{total}\nPayment: Mock UPI — Successful\nEstimated delivery: 3–4 days"
                )
            if self._has_tool_result_after_latest_user(messages, "get_order"):
                order_res = self._latest_tool_result(messages, "get_order")
                if order_res:
                    order_id = order_res.get("order_id", "ord_mock")
                    status = order_res.get("status", "placed")
                    items_desc = ", ".join(f"{item.get('name')} x{item.get('quantity')}" for item in order_res.get("items", []))
                    return ModelResponse(
                        content=f"Your order {order_id} is in status '{status}'. You bought: {items_desc}."
                    )

            tool_res = self._latest_tool_result(messages, "search_products")
            category_name = "products"
            if tool_res and tool_res.get("items"):
                first_item = tool_res["items"][0]
                category_name = first_item.get("category", "products").replace("_", " ")

            return ModelResponse(
                content=f"I found matching {category_name} from the catalog."
            )

        # Simulate the model deciding that a catalog search is required.
        is_search_intent = (
            matched_keyword is not None
            or "under" in user_message
            or "find" in user_message
            or "show" in user_message
            or "looking for" in user_message
            or "recommend" in user_message
            or "need" in user_message
            or "buy" in user_message
            or "rated" in user_message
            or "deal" in user_message
        )

        if is_search_intent:
            query = matched_keyword if matched_keyword else "products"
            if "shoes" in user_message or "shoe" in user_message:
                query = "running shoes"
            elif "wireless headphones" in user_message or "earbuds" in user_message:
                query = "wireless headphones"
            elif "headphones" in user_message or "headphone" in user_message:
                query = "headphones"
            elif "recovery" in user_message:
                query = "recovery"
            elif "beginner workout" in user_message or ("beginner" in user_message and "workout" in user_message):
                query = "beginner workout"
            elif "backpack" in user_message and "college" in user_message:
                query = "backpack college"
            elif "fitness watch" in user_message or "fitness watches" in user_message:
                query = "fitness watch"
            elif "gift" in user_message:
                query = "gift"
            elif "running" in user_message and "something" in user_message:
                query = "running"

            arguments: dict[str, Any] = {}
            if query != "products" or not ("rated" in user_message or "under" in user_message):
                arguments["query"] = query

            price_match = re.search(r"under\s*(?:₹|rs\.?)?\s*(\d+)", user_message)
            if price_match:
                arguments["max_price"] = int(price_match.group(1))

            if "best rated" in user_message or "highly rated" in user_message or "top rated" in user_message:
                arguments["min_rating"] = 4.7

            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        tool_name="search_products",
                        arguments=arguments,
                    )
                ]
            )

        # Normal conversational response.
        return ModelResponse(
            content="Hello! How can I help you?"
        )

    @staticmethod
    def _latest_user_message(
        messages: list[dict[str, Any]],
    ) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return str(message.get("content", "")).lower()
        return ""

    @classmethod
    def _search_product_ids(
        cls,
        messages: list[dict[str, Any]],
    ) -> list[str]:
        result = cls._latest_tool_result(messages, "search_products")
        if not result:
            return []

        return [
            str(item["product_id"])
            for item in result.get("items", [])
            if isinstance(item, dict) and "product_id" in item
        ]

    @staticmethod
    def _has_tool_result(
        messages: list[dict[str, Any]],
        tool_name: str,
    ) -> bool:
        return any(
            message.get("type") == "tool_result"
            and message.get("tool_name") == tool_name
            for message in messages
        )

    @staticmethod
    def _has_tool_result_after_latest_user(
        messages: list[dict[str, Any]],
        tool_name: str,
    ) -> bool:
        latest_user = max(
            (index for index, message in enumerate(messages) if message.get("role") == "user"),
            default=-1,
        )
        return any(
            message.get("type") == "tool_result"
            and message.get("tool_name") == tool_name
            for message in messages[latest_user + 1 :]
        )

    @staticmethod
    def _latest_tool_result(
        messages: list[dict[str, Any]],
        tool_name: str,
    ) -> dict[str, Any] | None:
        for message in reversed(messages):
            if (
                message.get("type") != "tool_result"
                or message.get("tool_name") != tool_name
            ):
                continue

            content = message.get("content", "")
            if not isinstance(content, str):
                return None

            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(content)
                except (SyntaxError, ValueError):
                    return None

            return parsed if isinstance(parsed, dict) else None

        return None

    @staticmethod
    def _latest_cart_id(
        messages: list[dict[str, Any]],
    ) -> str | None:
        for message in reversed(messages):
            if (
                message.get("type") == "tool_result"
                and message.get("tool_name") == "create_cart"
            ):
                match = re.search(
                    r"['\"]cart_id['\"]:\s*['\"]([^'\"]+)['\"]",
                    str(message.get("content", "")),
                )
                if match:
                    return match.group(1)
        return None