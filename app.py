import asyncio
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock
from types import SimpleNamespace

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel

from context import TWIN_SYSTEM_PROMPT
from tools import tools, handle_tool_calls

load_dotenv(override=True)

MODEL_NAME = "gpt-5.4-mini"
STATIC_DIR = Path(__file__).parent / "static"

# Cost/abuse guardrails for this unauthenticated public endpoint. All tunable via env vars
# without a code change, e.g. on Render's dashboard, so limits can be adjusted without a
# redeploy from source.
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", 8))
RATE_LIMIT_PER_DAY = int(os.environ.get("RATE_LIMIT_PER_DAY", 40))
GLOBAL_LIMIT_PER_DAY = int(os.environ.get("GLOBAL_LIMIT_PER_DAY", 300))
MAX_MESSAGE_CHARS = int(os.environ.get("MAX_MESSAGE_CHARS", 2000))
MAX_HISTORY_MESSAGES = int(os.environ.get("MAX_HISTORY_MESSAGES", 20))
MAX_TOOL_LOOPS = int(os.environ.get("MAX_TOOL_LOOPS", 4))
MAX_REPLY_TOKENS = int(os.environ.get("MAX_REPLY_TOKENS", 800))

client = AsyncOpenAI()

system = [{"role": "system", "content": TWIN_SYSTEM_PROMPT}]

app = FastAPI()


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


# ---------- Rate limiting ----------
# In-memory sliding windows. Resets on restart and isn't shared across instances, which is
# fine here: this is a cost guardrail for a low-traffic personal site, not a security
# boundary, so it doesn't need Redis or a database behind it.
_lock = Lock()
_ip_minute_hits: dict[str, deque] = defaultdict(deque)
_ip_day_hits: dict[str, deque] = defaultdict(deque)
_global_day_hits: deque = deque()


def _prune(hits, window_seconds, now):
    while hits and now - hits[0] > window_seconds:
        hits.popleft()


def check_rate_limit(client_ip):
    now = time.time()
    with _lock:
        minute_hits = _ip_minute_hits[client_ip]
        day_hits = _ip_day_hits[client_ip]
        _prune(minute_hits, 60, now)
        _prune(day_hits, 86400, now)
        _prune(_global_day_hits, 86400, now)

        if len(_global_day_hits) >= GLOBAL_LIMIT_PER_DAY:
            return "This site has hit its daily chat limit to keep API costs in check. Please try again tomorrow."
        if len(day_hits) >= RATE_LIMIT_PER_DAY:
            return "You've reached today's message limit for this chat. Please try again tomorrow."
        if len(minute_hits) >= RATE_LIMIT_PER_MINUTE:
            return "You're sending messages a bit fast, please wait a moment and try again."

        minute_hits.append(now)
        day_hits.append(now)
        _global_day_hits.append(now)
    return None


def client_ip(request: Request):
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def sanitise_history(history):
    # The client fully controls this payload, so never trust its shape or size: keep only
    # plain user/assistant text turns, cap each one's length, and cap how many we keep.
    cleaned = []
    for item in history[-MAX_HISTORY_MESSAGES:]:
        role = item.get("role") if isinstance(item, dict) else None
        content = item.get("content") if isinstance(item, dict) else None
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        cleaned.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
    return cleaned


# ---------- Chat ----------


def _accumulate_tool_calls(deltas, tool_calls):
    for delta in deltas:
        entry = tool_calls.setdefault(
            delta.index, {"id": None, "type": "function", "function": {"name": "", "arguments": ""}}
        )
        if delta.id:
            entry["id"] = delta.id
        if delta.function and delta.function.name:
            entry["function"]["name"] += delta.function.name
        if delta.function and delta.function.arguments:
            entry["function"]["arguments"] += delta.function.arguments


def _to_tool_call_objects(ordered_tool_calls):
    return [
        SimpleNamespace(
            id=tc["id"],
            function=SimpleNamespace(name=tc["function"]["name"], arguments=tc["function"]["arguments"]),
        )
        for tc in ordered_tool_calls
    ]


async def stream_reply(message, history):
    messages = system + history + [{"role": "user", "content": message}]

    for _ in range(MAX_TOOL_LOOPS):
        stream = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=tools,
            stream=True,
            max_completion_tokens=MAX_REPLY_TOKENS,
        )

        content = ""
        tool_calls = {}
        finish_reason = None

        async for chunk in stream:
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            if choice.delta.content:
                content += choice.delta.content
                yield choice.delta.content
            if choice.delta.tool_calls:
                _accumulate_tool_calls(choice.delta.tool_calls, tool_calls)

        if finish_reason != "tool_calls":
            return

        ordered_tool_calls = [tool_calls[i] for i in sorted(tool_calls)]
        messages.append(
            {"role": "assistant", "content": content or None, "tool_calls": ordered_tool_calls}
        )
        # handle_tool_calls does blocking HTTP (Pushover), so it doesn't tie up the event loop.
        results = await asyncio.to_thread(handle_tool_calls, _to_tool_call_objects(ordered_tool_calls))
        messages.extend(results)

    yield "\n\nSorry, that took more back-and-forth than I'm allowed. Please try rephrasing your question."


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest, request: Request):
    ip = client_ip(request)
    limit_message = check_rate_limit(ip)

    message = req.message.strip()

    def error_stream(text):
        async def gen():
            yield text

        return StreamingResponse(gen(), media_type="text/plain")

    if limit_message:
        return error_stream(limit_message)
    if not message:
        return error_stream("Please type a question first.")
    if len(message) > MAX_MESSAGE_CHARS:
        return error_stream(f"That message is a bit long, please keep it under {MAX_MESSAGE_CHARS} characters.")

    history = sanitise_history(req.history)

    async def event_stream():
        try:
            async for token in stream_reply(message, history):
                yield token
        except Exception as exc:  # noqa: BLE001 - surface a readable error to the chat UI
            print(f"Error while streaming reply: {exc}", flush=True)
            yield "\n\nSorry, something went wrong on my end, please try again."

    return StreamingResponse(event_stream(), media_type="text/plain")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
