import json
from uuid import uuid4

import httpx
from a2a.types import AgentCard, Message, Part, SendMessageRequest
from google.protobuf.json_format import MessageToDict, ParseDict

from auditor.errors import AgentFailure


async def invoke(url, payload, client=None):
    if client is None:
        async with httpx.AsyncClient(timeout=300) as own_client:
            return await invoke(url, payload, own_client)
    response = await client.get(url.rstrip("/") + "/.well-known/agent-card.json")
    response.raise_for_status()
    card = ParseDict(response.json(), AgentCard())
    if not any(i.protocol_binding == "JSONRPC" for i in card.supported_interfaces):
        raise ValueError("Agent does not advertise JSONRPC")
    # Call only the configured endpoint; do not follow card-supplied URLs.
    request = SendMessageRequest(
        message=Message(message_id=str(uuid4()), role=1, parts=[Part(text=json.dumps(payload))])
    )
    response = await client.post(
        url,
        headers={"A2A-Version": "1.0"},
        json={
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "SendMessage",
            "params": MessageToDict(request),
        },
    )
    response.raise_for_status()
    body = response.json()
    if "error" in body:
        raise RuntimeError("A2A agent returned an error")
    result = json.loads(body["result"]["message"]["parts"][0]["text"])
    if "agent_error" in result:
        raise AgentFailure(result["agent_error"])
    return result
