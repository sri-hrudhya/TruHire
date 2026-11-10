"""The assistant as a tool-calling agent: a fake model drives real tools against the test database."""
import json
import uuid

import pytest

from test_location_role_filters import env  # noqa: F401  (fixture)
from backend.models import Candidate, Position, RequirementCandidateStatus


class FakeModel:
    """Plays a scripted conversation: each entry is one assistant message (content and/or tool calls)."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.calls = []

    def __call__(self, messages, tools, **kwargs):
        self.calls.append(messages)
        return self.turns.pop(0)


def call(name, **args):
    return {"id": uuid.uuid4().hex[:8], "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def say(text):
    return {"role": "assistant", "content": text}


def use(*calls):
    return {"role": "assistant", "content": None, "tool_calls": list(calls)}


def ask(env, message, **extra):
    return env["client"].post("/api/assistant/message", headers=env["headers"], json={"message": message, **extra})


@pytest.fixture
def agent_env(env, monkeypatch):
    def install(*turns):
        model = FakeModel(*turns)
        monkeypatch.setattr("backend.services.llm.agent.chat_with_tools", model)
        return model
    env["install"] = install
    return env


def _named(env, name):
    candidate = env["db"].get(Candidate, env["make"]())
    candidate.candidate_name = name
    env["db"].commit()
    return candidate


def test_open_positions_come_from_the_get_demand_tool(agent_env):
    position = agent_env["db"].get(Position, agent_env["make_jd"]())
    position.no_of_positions = 7
    agent_env["db"].commit()
    model = agent_env["install"](use(call("get_demand", demand=position.display_id)), say("It has 7 open positions."))

    body = ask(agent_env, f"how many open positions does {position.display_id} have?").json()

    assert body["reply"] == "It has 7 open positions."
    assert body["action"] == "open_positions" and body["requirements"][0]["no_of_positions"] == 7
    tool_result = model.calls[1][-1]
    assert tool_result["role"] == "tool" and "untrusted_data" in tool_result["content"] and '"no_of_positions": 7' in tool_result["content"]


def test_candidate_history_by_name_uses_the_history_tool(agent_env):
    candidate = _named(agent_env, f"Ravi Kumar{agent_env['tag']}")
    position_id = agent_env["make_jd"]()
    agent_env["db"].get(Position, position_id).client_name = "IBM"
    agent_env["db"].commit()
    agent_env["client"].put(f"/api/job-descriptions/{position_id}/candidates/{candidate.id}/status", headers=agent_env["headers"], json={"status": "Shortlisted"})
    agent_env["install"](use(call("get_candidate_history", candidate=f"Ravi Kumar{agent_env['tag']}")), say("Ravi is shortlisted for IBM."))

    body = ask(agent_env, "tell me about candidate Ravi Kumar").json()

    assert body["action"] == "candidate_history"
    assert [(r["client_name"], r["status"]) for r in body["requirements"]] == [("IBM", "Shortlisted")]


def test_best_matches_for_a_demand_id_carry_scores_and_gaps(agent_env, monkeypatch):
    position = agent_env["db"].get(Position, agent_env["make_jd"]())
    candidate = _named(agent_env, "Asha Rao")
    fake = {"results": [{"candidate": {"id": candidate.id, "display_id": candidate.display_id, "candidate_name": "Asha Rao"}, "match_score": 81.5,
                         "score_breakdown": {"matched_skills": ["Python"], "missing_skills": ["Docker"]}}], "total_matches": 1}
    monkeypatch.setattr("backend.services.llm.agent.execute_candidate_search", lambda db, **kw: fake)
    model = agent_env["install"](use(call("match_candidates", demand=position.display_id, top_n=3)), say("Asha Rao fits at 81.5%."))

    body = ask(agent_env, f"best candidates for {position.display_id}").json()

    assert body["action"] == "matches" and body["results"][0]["match_score"] == 81.5
    assert '"missing_skills": ["Docker"]' in model.calls[1][-1]["content"]


def test_status_change_waits_for_confirmation_and_runs_once(agent_env):
    candidate = _named(agent_env, "Meera Iyer")
    position_id = agent_env["make_jd"]()
    position = agent_env["db"].get(Position, position_id)
    agent_env["install"](use(call("update_requirement_status", candidate="Meera Iyer", demand=position.display_id, status="Shortlisted")))

    body = ask(agent_env, f"shortlist Meera Iyer for {position.display_id}").json()

    assert body["action"] == "confirm_action"
    pending = body["pending"]
    assert set(pending) == {"id", "tool", "args", "summary"} and pending["tool"] == "update_requirement_status"
    assert "Meera Iyer" in pending["summary"] and "Shortlisted" in pending["summary"]
    agent_env["db"].expire_all()
    assert agent_env["db"].query(RequirementCandidateStatus).filter_by(candidate_id=candidate.id).count() == 0  # nothing changed yet

    confirm = {"conversation_id": body["conversation_id"], "pending_id": pending["id"], "approve": True}
    done = agent_env["client"].post("/api/assistant/confirm", headers=agent_env["headers"], json=confirm)
    assert done.status_code == 200 and done.json()["action"] == "action_done"
    agent_env["db"].expire_all()
    row = agent_env["db"].query(RequirementCandidateStatus).filter_by(candidate_id=candidate.id, position_id=position_id).one()
    assert row.status == "Shortlisted" and row.updated_by == agent_env["user"].id

    again = agent_env["client"].post("/api/assistant/confirm", headers=agent_env["headers"], json=confirm)
    assert again.status_code == 409  # the id is single use


def test_rejecting_a_proposed_change_leaves_data_alone(agent_env):
    candidate = _named(agent_env, "Kiran Das")
    agent_env["install"](use(call("set_availability", candidate="Kiran Das", availability="Not Active")))

    body = ask(agent_env, "mark Kiran Das not active").json()
    assert body["action"] == "confirm_action"
    rejected = agent_env["client"].post("/api/assistant/confirm", headers=agent_env["headers"],
                                        json={"conversation_id": body["conversation_id"], "pending_id": body["pending"]["id"], "approve": False})

    assert rejected.json()["action"] == "action_rejected"
    agent_env["db"].expire_all()
    assert (agent_env["db"].get(Candidate, candidate.id).availability_status or "Active") == "Active"


def test_confirmation_is_scoped_to_the_owner(agent_env):
    _named(agent_env, "Nila Sen")
    agent_env["install"](use(call("set_availability", candidate="Nila Sen", availability="Not Active")))
    body = ask(agent_env, "mark Nila Sen not active").json()

    wrong = agent_env["client"].post("/api/assistant/confirm", headers=agent_env["headers"],
                                     json={"conversation_id": "not-mine", "pending_id": body["pending"]["id"]})
    assert wrong.status_code == 404
    unknown = agent_env["client"].post("/api/assistant/confirm", headers=agent_env["headers"],
                                       json={"conversation_id": body["conversation_id"], "pending_id": "nope"})
    assert unknown.status_code == 404


def test_off_topic_message_is_refused_without_calling_the_model(agent_env):
    model = agent_env["install"]()
    body = ask(agent_env, "write me a poem about the ocean").json()
    assert body["action"] == "reply" and "only help with TruHire" in body["reply"]
    assert model.calls == []


def test_remember_saves_a_note_for_later_chats(agent_env):
    agent_env["install"](use(call("remember", note="prefers Pune demands")), say("Noted."),
                         say("Okay."))
    ask(agent_env, "remember that I prefer Pune demands")
    model = agent_env["install"](say("Pune it is."))
    ask(agent_env, "show my demands")
    assert "prefers Pune demands" in model.calls[0][0]["content"]


def test_agent_failure_falls_back_to_the_keyword_handlers(env):
    # conftest makes chat_with_tools raise, as when no provider is reachable
    position = env["db"].get(Position, env["make_jd"]())
    position.no_of_positions = 3
    env["db"].commit()
    body = ask(env, f"number of open positions of {position.display_id}").json()
    assert body["action"] == "open_positions" and "3 open positions" in body["reply"]
