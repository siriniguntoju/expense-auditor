from uuid import uuid4

from google.adk.agents import BaseAgent, SequentialAgent
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from auditor.mcp_client import call, tool_session


class ConvertAgent(BaseAgent):
    async def _run_async_impl(self, ctx):
        conversions = {}
        async with tool_session("tools_mcp.currency") as session:
            for e in ctx.session.state["packet"]["report"]["expenses"]:
                conversions[e["id"]] = await call(
                    session, "convert_currency", dict(amount=e["amount"], currency=e["currency"])
                )
        packet = dict(ctx.session.state["packet"], conversions=conversions)
        yield Event(author=self.name, actions=EventActions(state_delta={"packet": packet}))


class CheckAgent(BaseAgent):
    async def _run_async_impl(self, ctx):
        packet = ctx.session.state["packet"]
        async with tool_session("tools_mcp.policy") as session:
            result = await call(
                session,
                "check_policy",
                dict(
                    report=packet["report"],
                    conversions=packet["conversions"],
                    receipts=packet["receipts"],
                ),
            )
        yield Event(
            author=self.name, actions=EventActions(state_delta={"packet": dict(packet, **result)})
        )


async def run_policy(packet):
    sessions = InMemorySessionService()
    sid = str(uuid4())
    await sessions.create_session(
        app_name="expense_policy", user_id="synthetic", session_id=sid, state={"packet": packet}
    )
    agent = SequentialAgent(
        name="policy_workflow",
        sub_agents=[ConvertAgent(name="currency"), CheckAgent(name="policy")],
    )
    runner = Runner(agent=agent, app_name="expense_policy", session_service=sessions)
    async for _ in runner.run_async(
        user_id="synthetic",
        session_id=sid,
        new_message=types.Content(
            role="user", parts=[types.Part(text="Check the synthetic report.")]
        ),
    ):
        pass
    session = await sessions.get_session(
        app_name="expense_policy", user_id="synthetic", session_id=sid
    )
    return session.state["packet"]
