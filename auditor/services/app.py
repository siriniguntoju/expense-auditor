import json
import os
from contextlib import asynccontextmanager
from uuid import uuid4

from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Message, Part
from starlette.applications import Starlette

from auditor.checks import audit
from auditor.intake import fixture_intake
from auditor.policy_agent import run_policy


class Executor(AgentExecutor):
    def __init__(self, role):
        self.role = role

    async def execute(self, context, event_queue):
        payload = json.loads(context.get_user_input())
        if self.role == "intake":
            result = fixture_intake(payload["report_id"])
        elif self.role == "policy":
            result = await run_policy(payload)
        else:
            result = audit(payload)
        await event_queue.enqueue_event(
            Message(message_id=str(uuid4()), role=2, parts=[Part(text=json.dumps(result))])
        )

    async def cancel(self, context, event_queue):
        raise NotImplementedError("Immediate-response agents do not support task cancellation")


def create_app(role, url):
    if role not in {"intake", "policy", "audit"}:
        raise ValueError("Unknown agent role")
    card = AgentCard(
        name=f"Expense {role}",
        description=f"Synthetic expense {role} agent",
        version="0.1.0",
        supported_interfaces=[
            AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(id=role, name=role, description=f"Run {role}", tags=["synthetic-expenses"])
        ],
    )
    handler = DefaultRequestHandler(
        agent_executor=Executor(role), task_store=InMemoryTaskStore(), agent_card=card
    )

    @asynccontextmanager
    async def lifespan(app):
        yield
        await handler.aclose()

    return Starlette(
        routes=create_agent_card_routes(card) + create_jsonrpc_routes(handler, "/"),
        lifespan=lifespan,
    )


role = os.getenv("AGENT_ROLE", "intake")
app = create_app(role, os.getenv("AGENT_URL", "http://localhost:8211/"))
