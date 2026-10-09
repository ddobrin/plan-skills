import json

import tally


def write(tmp_path, name, obj, fence=False):
    p = tmp_path / name
    body = json.dumps(obj)
    p.write_text(f"```json\n{body}\n```\n" if fence else body)
    return str(p)


def f(ident, real=True, sev="high", file="src/a.py", **kw):
    return {"id": ident, "isReal": real, "correctedSeverity": sev, "file": file, **kw}


def run(tmp_path, capsys, verdicts, gate=None):
    paths = [write(tmp_path, f"s{i}.json", v, fence=(i == 0)) for i, v in enumerate(verdicts)]
    args = (["--gate", str(gate)] if gate else []) + paths
    assert tally.main(args) == 0
    return json.loads(capsys.readouterr().out)


def test_two_of_three_confirms_and_one_vote_is_unconfirmed(tmp_path, capsys):
    out = run(tmp_path, capsys, [
        {"findings": [f("race"), f("npe", sev="low")]},
        {"findings": [f("race", sev="critical")]},
        {"findings": []},
    ])
    assert out["mode"] == "finding" and out["gate"] == 2
    assert [e["id"] for e in out["confirmed"]] == ["race"]
    assert [e["id"] for e in out["unconfirmed"]] == ["npe"]
    race = out["confirmed"][0]
    assert race["votes"] == 2 and race["reported_by"] == [1, 2]
    # tie between high and critical goes to the higher level
    assert race["severity"] == "critical"
    assert sorted(race["severity_votes"]) == ["critical", "high"]


def test_same_id_in_different_files_counts_separately(tmp_path, capsys):
    out = run(tmp_path, capsys, [
        {"findings": [f("dup", file="a.py")]},
        {"findings": [f("dup", file="b.py")]},
        {"findings": []},
    ])
    assert out["confirmed"] == [] and len(out["unconfirmed"]) == 2


def test_is_real_false_everywhere_is_rejected(tmp_path, capsys):
    out = run(tmp_path, capsys, [
        {"findings": [f("style", real=False)]},
        {"findings": [f("style", real=False)]},
        {"findings": []},
    ])
    assert [e["id"] for e in out["rejected"]] == ["style"]


def test_gate_one_and_three(tmp_path, capsys):
    verdicts = [{"findings": [f("x")]}, {"findings": [f("x")]}, {"findings": []}]
    assert [e["id"] for e in run(tmp_path, capsys, verdicts, gate=1)["confirmed"]] == ["x"]
    assert run(tmp_path, capsys, verdicts, gate=3)["confirmed"] == []


def test_first_domino_votes(tmp_path, capsys):
    out = run(tmp_path, capsys, [
        {"findings": [], "first_domino": "step-2-missing-table"},
        {"findings": [], "first_domino": "step-2-missing-table"},
        {"findings": [], "first_domino": "step-4-order"},
    ])
    assert out["first_domino_votes"] == {"step-2-missing-table": 2, "step-4-order": 1}


def test_claim_refutation_mode(tmp_path, capsys):
    claim = "safe under concurrent requests"
    out = run(tmp_path, capsys, [
        {"claim": claim, "refuted": True, "correctedSeverity": "high", "attack": "two logins"},
        {"claim": claim, "refuted": True, "correctedSeverity": "medium", "attack": "burst"},
        {"claim": claim, "refuted": False, "attack": "tried"},
    ])
    assert out["mode"] == "claim-refutation"
    assert out["failed_claims"][0]["refuted_by"] == 2


def test_unreadable_input_exits_2(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert tally.main([str(bad)]) == 2
