"""LogScribe's Ironclad config and seeded incidents (logscribe/) stay valid,
and seeded messages use the same "CODE: message" shape the bank logs."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "logscribe"


def test_config_watches_both_services():
    cfg = tomllib.loads((ROOT / "ironclad.toml").read_text())
    assert cfg["collection"] == "ironclad_errors"
    assert {s["service"] for s in cfg["sources"]} == {"bank-service", "agent-service"}
    assert (ROOT / cfg["seeds"]).exists()


def test_seeds_are_marked_and_complete():
    data = json.loads((ROOT / "seed_incidents.json").read_text())
    assert data["seeded_examples"] is True and "SEEDED EXAMPLES" in data["note"]
    ids = [i["id"] for i in data["incidents"]]
    assert len(ids) == len(set(ids))
    for incident in data["incidents"]:
        for field in ("service_name", "error_type", "message", "symptom", "cause", "fix"):
            assert incident.get(field), (incident["id"], field)
        assert incident["service_name"] in ("bank-service", "agent-service")
        if incident["error_type"].isupper():  # a BankError code: logged as "CODE: message"
            assert incident["message"].startswith(incident["error_type"] + ": ")
