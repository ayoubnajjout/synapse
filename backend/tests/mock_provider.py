"""Local OpenAI-compatible test server. Never used by the application itself.

Run: uvicorn mock_provider:app --app-dir backend/tests --port 8131
Use endpoint http://127.0.0.1:8131/v1 and model mock-model.
"""

import asyncio
import json
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()


@app.get("/v1/models")
async def models():
    return {"data": [{"id": "mock-model"}, {"id": "another-model"}, {"id": "future-model"}]}


@app.post("/v1/chat/completions")
async def completion(request: Request):
    body = await request.json()
    messages = body["messages"]
    last = messages[-1]["content"]
    if "simulate-error" in last:
        return JSONResponse({"error": {"message": "Mock provider unavailable", "type": "server_error"}}, status_code=503)
    memories = "PostgreSQL" in messages[0]["content"]
    response = f"This is a **mock response** from `{body['model']}`. "
    response += f"I received {len(messages) - 1} history messages. "
    if memories:
        response += "Your saved preference for PostgreSQL is included. "
    response += "\n\n```python\nprint('Hello, Synapse!')\n```\n\nYour conversation context stays with you."

    async def stream():
        delay = 0.3 if "simulate-slow" in last else 0.01
        for index in range(0, len(response), 8):
            await asyncio.sleep(delay)
            chunk = {"id": "chatcmpl-mock", "object": "chat.completion.chunk", "created": int(time.time()),
                     "model": body["model"], "choices": [{"index": 0, "delta": {"content": response[index:index + 8]}, "finish_reason": None}]}
            yield f"data: {json.dumps(chunk)}\n\n"
        yield f'data: {json.dumps({"id": "chatcmpl-mock", "object": "chat.completion.chunk", "created": int(time.time()), "model": body["model"], "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})}\n\n'
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
