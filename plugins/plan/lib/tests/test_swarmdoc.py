import json
import os

import pytest

import swarmdoc
from conftest import PLUGIN


def test_extract_finds_tagged_block_and_ignores_prose():
    text = "# Title\n\nSome prose with ```inline``` fences.\n\n```json swarm-config\n{\"a\": 1}\n```\nmore\n"
    assert swarmdoc.extract(text, "swarm-config") == {"a": 1}


def test_extract_ignores_other_tags_and_untagged_blocks():
    text = "```json\n{\"x\": 0}\n```\n```json other\n{\"y\": 1}\n```\n```json swarm-config\n{\"z\": 2}\n```\n"
    assert swarmdoc.extract(text, "swarm-config") == {"z": 2}


def test_extract_requires_exactly_one_block():
    with pytest.raises(swarmdoc.SwarmDocError, match="no ```json swarm-config"):
        swarmdoc.extract("nothing here", "swarm-config")
    two = "```json t\n{}\n```\n```json t\n{}\n```\n"
    with pytest.raises(swarmdoc.SwarmDocError, match="exactly one"):
        swarmdoc.extract(two, "t")


def test_extract_reports_invalid_json():
    with pytest.raises(swarmdoc.SwarmDocError, match="not valid JSON"):
        swarmdoc.extract("```json t\n{broken\n```\n", "t")


def test_topology_file_parses_and_is_consistent():
    graph = swarmdoc.extract_file(os.path.join(PLUGIN, "topology.md"), "plan-swarm-topology")
    ids = {n["id"] for n in graph["nodes"]}
    refs = [x for edge in graph["flow"] for x in edge]
    refs += [l["from"] for l in graph["loops"]] + [l["to"] for l in graph["loops"]]
    refs += [n[k] for n in graph["nodes"] for k in ("attaches_to", "returns_to", "replaces") if k in n]
    assert set(refs) <= ids
    assert [l["n"] for l in graph["loops"]] == list(range(1, 9))
    assert set(graph["config_keys"]) >= {"engineers.max_concurrent", "audit.max_path_a_rounds"}


def test_topology_actors_are_roles_or_runtime_actors():
    graph = swarmdoc.extract_file(os.path.join(PLUGIN, "topology.md"), "plan-swarm-topology")
    roles = {f[:-3] for f in os.listdir(os.path.join(PLUGIN, "roles")) if f.endswith(".md")}
    actors = {n["actor"] for n in graph["nodes"] if "actor" in n}
    assert actors <= roles | {"human", "research", "triage"}, actors - roles
    for n in graph["nodes"]:
        if n["kind"] in ("add-on", "swap-in") and n["id"] != "local-mode":
            assert n["id"] in roles, n["id"]
            assert os.path.exists(os.path.join(PLUGIN, "agents", n["id"], "agent.md"))


def test_template_swarm_md_is_valid():
    cfg = swarmdoc.validate_config(
        swarmdoc.extract_file(os.path.join(PLUGIN, "templates", "swarm.md"), "swarm-config"))
    assert cfg["engineers"]["max_concurrent"] == 5
    assert cfg["audit"]["max_path_a_rounds"] == 3


def test_validate_config_fills_defaults():
    cfg = swarmdoc.validate_config({"version": 1})
    assert cfg["delivery"] == {"mode": "pr", "host": "github"}
    assert cfg["engineers"]["max_concurrent"] == 5
    assert cfg["approvals"]["nonce_ttl_minutes"] == 15


@pytest.mark.parametrize("raw, message", [
    ({"version": 2}, "version must be 1"),
    ({"delivery": {"mode": "ftp"}}, "delivery.mode"),
    ({"engineers": {"max_concurrent": 0}}, "engineers.max_concurrent"),
    ({"engineers": {"max_concurrent": True}}, "engineers.max_concurrent"),
    ({"engineers": {"max": 3}}, "unknown engineers keys"),
    ({"tier": {}}, "unknown swarm-config keys"),
    ({"tiers": {"routine": {}}}, "only \"elevated\" and \"critical\""),
    ({"tiers": {"critical": {"paths": "auth/**"}}}, "tiers.critical.paths"),
    ({"policies": ["ok", ""]}, "policies"),
])
def test_validate_config_rejects_bad_values(raw, message):
    with pytest.raises(swarmdoc.SwarmDocError, match=message):
        swarmdoc.validate_config(raw)


def test_load_config_from_repo(repo):
    cfg = swarmdoc.load_config()
    assert cfg["tiers"]["critical"]["paths"] == ["**/auth/**", "migrations/**"]
    os.remove(repo / "plans" / "swarm.md")
    with pytest.raises(swarmdoc.SwarmDocError, match="cannot read"):
        swarmdoc.load_config()


@pytest.mark.parametrize("path, pattern, ok", [
    ("src/auth/login.ts", "**/auth/**", True),
    ("auth/login.ts", "**/auth/**", True),
    ("src/authz/login.ts", "**/auth/**", False),
    ("migrations/001.sql", "migrations/**", True),
    ("db/migrations/001.sql", "migrations/**", False),
    ("api/v1/users.py", "api/*/users.py", True),
    ("api/v1/x/users.py", "api/*/users.py", False),
    (".github/workflows/ci.yml", ".github/**", True),
    ("./src/auth/x.ts", "**/auth/**", True),
])
def test_path_matches(path, pattern, ok):
    assert swarmdoc.path_matches(path, pattern) is ok


def test_cli_prints_block(tmp_path, capsys):
    f = tmp_path / "x.md"
    f.write_text("```json t\n{\"k\": [1]}\n```\n")
    assert swarmdoc.main([str(f), "t"]) == 0
    assert json.loads(capsys.readouterr().out) == {"k": [1]}
    assert swarmdoc.main([str(f), "missing"]) == 2
