"""HTTP front for the travel concierge: an OpenAI-style chat endpoint backed by a Google ADK agent tree."""

import asyncio
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

import config

ENV = config.require_env()

from concierge.agents import build_root  # noqa: E402  (needs the environment checked first)

APP_NAME = "travel_concierge"
USER_ID = "traveler"

_sessions = InMemorySessionService()
_runner = Runner(agent=build_root(ENV), app_name=APP_NAME, session_service=_sessions)

_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()

FALLBACK = "Sorry, I could not finish that request. Please try again."


def _text_of(content) -> str:
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


def _history(messages: list[dict]) -> tuple[list[tuple[str, str]], str]:
    """Split the chat into earlier user/assistant turns and the final user message."""
    turns = [(m["role"], _text_of(m.get("content"))) for m in messages if m.get("role") in ("user", "assistant")]
    turns = [(r, t) for r, t in turns if t.strip()]
    if not turns or turns[-1][0] != "user":
        raise ValueError("the last message must be from the user")
    return turns[:-1], turns[-1][1]


def _tool_failed(result) -> bool:
    return isinstance(result, dict) and bool(result.get("error"))


async def _run(messages: list[dict]) -> tuple[str, list[dict]]:
    earlier, question = _history(messages)
    session = await _sessions.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=uuid.uuid4().hex)
    try:
        calls: dict[str, dict] = {}
        order: list[str] = []
        reply = ""

        async def drive(text: str) -> str:
            found = ""
            message = types.Content(role="user", parts=[types.Part(text=text)])
            try:
                async for event in _runner.run_async(
                    user_id=USER_ID, session_id=session.id, new_message=message,
                    run_config=RunConfig(max_llm_calls=config.MAX_LLM_CALLS),
                ):
                    for call in event.get_function_calls():
                        if call.name == "transfer_to_agent":
                            continue
                        key = call.id or f"{call.name}-{len(order)}"
                        calls[key] = {"id": key, "name": call.name, "arguments": dict(call.args or {}), "result": None, "error": False}
                        order.append(key)
                    for resp in event.get_function_responses():
                        key = resp.id if resp.id in calls else next((k for k in order if calls[k]["name"] == resp.name and calls[k]["result"] is None), None)
                        if key:
                            calls[key]["result"] = resp.response
                            calls[key]["error"] = _tool_failed(resp.response)
                    if event.is_final_response() and event.content and event.author != "user":
                        text = "".join(p.text or "" for p in event.content.parts or [] if not getattr(p, "thought", False))
                        if text.strip():
                            found = text.strip()
            except Exception as exc:  # the model or a tool round failed; still answer
                print(f"run failed: {type(exc).__name__}: {str(exc)[:300]}", flush=True)
            return found

        if earlier:
            lines = [("Traveler: " if r == "user" else "Concierge: ") + t for r, t in earlier[-config.HISTORY_MESSAGES:]]
            question = "Conversation so far:\n" + "\n".join(lines) + "\n\nThe traveler's latest message (reply to this):\n" + question
        reply = await drive(question)
        if not reply:
            reply = await drive("Please give the traveler your answer now.")
        return reply or FALLBACK, [calls[k] for k in order]
    finally:
        await _sessions.delete_session(app_name=APP_NAME, user_id=USER_ID, session_id=session.id)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.split("?")[0] == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.split("?")[0] not in ("/v1/chat/completions", "/chat/completions"):
            return self._send(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            messages = body["messages"]
            future = asyncio.run_coroutine_threadsafe(_run(messages), _loop)
            reply, tools = future.result(timeout=280)
        except (KeyError, ValueError, TypeError) as exc:
            return self._send(400, {"error": {"message": f"bad request: {exc}"}})
        except Exception as exc:
            print(f"request failed: {type(exc).__name__}: {exc}", flush=True)
            reply, tools = FALLBACK, []
        self._send(200, {
            "id": "chatcmpl-" + uuid.uuid4().hex[:12], "object": "chat.completion", "created": int(time.time()),
            "model": ENV["LLM_MODEL"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
            "completed_tools": tools,
        })

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"travel concierge listening on :{config.PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", config.PORT), Handler).serve_forever()
