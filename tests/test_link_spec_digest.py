"""A stored link run's file name hashes the spec's linking parts only: the quality declarations (outcome.known, a pass's
known_only) choose no pair, so adding them must not orphan the stored runs (t07, 2026-11-23)."""
import copy

from pegasus_data.linkage import store


def test_quality_keys_do_not_move_the_digest(monkeypatch):
    links = copy.deepcopy(store.raw_links())
    name = "sih_admissions_to_sim"
    before = store._spec_digest(name)
    body = links["links"][name]
    if isinstance(body.get("outcome"), dict):
        body["outcome"].pop("known", None)
    for part in (body, body.get("deterministic") or {}, body.get("probabilistic") or {}):
        for p in part.get("passes") or []:
            if isinstance(p, dict):
                p.pop("known_only", None)
    monkeypatch.setattr(store, "raw_links", lambda: links)
    assert store._spec_digest(name) == before
    body["outcome"]["origin"] = "admission.end"     # a linking change still moves it
    assert store._spec_digest(name) != before
