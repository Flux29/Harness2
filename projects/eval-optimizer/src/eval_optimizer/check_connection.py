"""Phase 0 exit check: prove GLM 5.1 on NVIDIA Build answers AND can tool-call.

Uses the raw `openai` client (not the harness) so this check has no dependency on
harness internals — it isolates "is the endpoint usable?" from "is the agent code
right?". Run: `uv run python -m eval_optimizer.check_connection`
"""
from __future__ import annotations

from openai import OpenAI
from openai.types.chat import ChatCompletionToolParam

from .config import Settings


def main() -> int:
    s = Settings.from_env()
    # from_env() no longer validates provider keys (Phase 4.1); this check
    # targets the NVIDIA endpoint specifically, so require its key here.
    if not s.nvidia_api_key:
        print("FAIL: NVIDIA_API_KEY is not set — this check targets the NVIDIA endpoint.")
        return 1
    client = OpenAI(base_url=s.nvidia_base_url, api_key=s.nvidia_api_key)
    print(f"Endpoint: {s.nvidia_base_url}")
    print(f"Model:    {s.glm_model}\n")

    # 1) Basic chat completion ------------------------------------------------
    chat = client.chat.completions.create(
        model=s.glm_model,
        messages=[{"role": "user", "content": "Reply with exactly one word: PONG"}],
        max_tokens=16,
    )
    reply = (chat.choices[0].message.content or "").strip()
    print(f"chat reply: {reply!r}")
    if not reply:
        print("FAIL: empty chat response.")
        return 1

    # 2) Tool-calling round-trip (the real risk on a free endpoint) -----------
    tools: list[ChatCompletionToolParam] = [
        {
            "type": "function",
            "function": {
                "name": "add",
                "description": "Add two integers and return the sum.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"},
                    },
                    "required": ["a", "b"],
                },
            },
        }
    ]
    tc = client.chat.completions.create(
        model=s.glm_model,
        messages=[{"role": "user", "content": "Use the add tool to add 21 and 21."}],
        tools=tools,
        tool_choice="auto",
        max_tokens=256,
    )
    msg = tc.choices[0].message
    if not msg.tool_calls:
        print(f"FAIL: model did not emit a tool call. It said: {msg.content!r}")
        return 1

    call = msg.tool_calls[0]
    if call.type != "function":
        print(f"FAIL: unexpected tool-call type {call.type!r}.")
        return 1
    print(f"tool call:  {call.function.name}({call.function.arguments})")
    print("\nPhase 0 PASSED: chat + tool calling both work on this endpoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
