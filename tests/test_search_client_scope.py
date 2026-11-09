from backend.models import Position
from uuid import uuid4
from test_location_role_filters import env, retrieval, _hits


def _create_jd(env, tag, client, status="Open"):
    position_id = env["make_jd"]("Python engineer with API and database experience.", f"{tag} Engineer")
    position = env["db"].get(Position, position_id)
    position.client_name = client
    position.status = status
    env["db"].commit()
    return position_id


def test_client_search_groups_candidates_under_each_non_cancelled_jd(env, retrieval):
    a, b = env["make"](), env["make"]()
    client = f"Acme {uuid4().hex}"
    open_one = _create_jd(env, "Client A", client)
    open_two = _create_jd(env, "Client B", client.upper())
    cancelled = _create_jd(env, "Closed", client, "Cancelled")
    retrieval["vector"], retrieval["lexical"] = _hits(a, b), _hits(b, a)

    response = env["client"].post("/api/search", headers=env["headers"], json={"client_name": f"  {client.lower()} ", "query": "python"})
    body = response.json()

    assert response.status_code == 200
    assert [group["position"]["id"] for group in body["client_groups"]] == [open_two, open_one]
    assert all({item["candidate"]["id"] for item in group["results"]} == {a, b} for group in body["client_groups"])
    assert cancelled not in [group["position"]["id"] for group in body["client_groups"]]


def test_search_clients_lists_only_saved_non_cancelled_client_names(env):
    client = f"Acme {uuid4().hex}"
    _create_jd(env, "Open", client)
    _create_jd(env, "Closed", f"Old {uuid4().hex}", "Cancelled")

    response = env["client"].get("/api/search/clients", headers=env["headers"])

    assert response.status_code == 200
    names = response.json()
    assert client in names
    assert not any(name.startswith("Old ") for name in names)


def test_assistant_searches_candidates_for_a_client_with_jd_groups(env, retrieval):
    candidate = env["make"]()
    client = f"Recruiting {uuid4().hex}"
    position_id = _create_jd(env, "Platform", client)
    retrieval["vector"], retrieval["lexical"] = _hits(candidate), _hits(candidate)

    response = env["client"].post("/api/assistant/message", headers=env["headers"], json={
        "message": f"Find candidates for {client}"
    })

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "client_candidate_matches"
    assert body["client_groups"][0]["position"]["id"] == position_id
    assert body["client_groups"][0]["results"][0]["candidate"]["id"] == candidate
