import pytest

import render_roles


ROLE = """<!-- note for editors -->
<!-- @agent:frontmatter -->
---
name: demo
tools: [Read]
---
<!-- @end -->
<!-- @skill:frontmatter -->
---
name: demo
description: a demo
---
<!-- @end -->
<!-- @body -->
shared top
<!-- @agent -->
agent only
<!-- @end -->
<!-- @skill -->
skill only
<!-- @end -->
shared bottom
"""


def test_parse_splits_forms():
    out = render_roles.parse(ROLE, "demo")
    assert out["agent"] == "---\nname: demo\ntools: [Read]\n---\nshared top\nagent only\nshared bottom\n"
    assert out["skill"] == "---\nname: demo\ndescription: a demo\n---\nshared top\nskill only\nshared bottom\n"


def test_role_without_agent_frontmatter_has_no_agent_form():
    text = ROLE.split("<!-- @skill:frontmatter -->")[1]
    out = render_roles.parse("<!-- @skill:frontmatter -->" + text, "demo")
    assert set(out) == {"skill"}


@pytest.mark.parametrize("broken, message", [
    (ROLE.replace("<!-- @body -->\n", ""), "missing"),
    (ROLE.replace("name: demo\ntools", "name: other\ntools"), "must declare"),
    (ROLE.replace("agent only\n<!-- @end -->", "agent only"), "nested"),
    (ROLE + "<!-- @end -->\n", "@end without an open block"),
])
def test_parse_rejects_malformed_roles(broken, message):
    with pytest.raises(render_roles.RoleError, match=message):
        render_roles.parse(broken, "demo")


def test_repository_roles_render_and_are_in_sync():
    outputs = render_roles.render_all()
    assert any(p.endswith("agents/supervisor/agent.md") for p in outputs)
    assert any(p.endswith("skills/simplifier/SKILL.md") for p in outputs)
    assert any(p.endswith("agents/visual-architect/assets/template.html") for p in outputs)
    assert render_roles.main(["--check"]) == 0


def test_render_writes_antigravity_layout_and_mirrors_resources(tmp_path, capsys):
    (tmp_path / "roles").mkdir()
    (tmp_path / "roles" / "demo.md").write_text(ROLE)
    (tmp_path / "skills" / "demo" / "assets").mkdir(parents=True)
    (tmp_path / "skills" / "demo" / "assets" / "t.html").write_text("<html></html>\n")
    assert render_roles.main(["--check"], plugin=str(tmp_path)) == 1  # nothing generated yet
    assert render_roles.main([], plugin=str(tmp_path)) == 0
    assert (tmp_path / "agents" / "demo" / "agent.md").read_text().startswith("---\nname: demo")
    assert (tmp_path / "skills" / "demo" / "SKILL.md").exists()
    assert (tmp_path / "agents" / "demo" / "assets" / "t.html").read_text() == "<html></html>\n"
    assert render_roles.main(["--check"], plugin=str(tmp_path)) == 0
    (tmp_path / "agents" / "demo" / "assets" / "t.html").write_text("drift")
    assert render_roles.main(["--check"], plugin=str(tmp_path)) == 1
    assert "agents/demo/assets/t.html" in capsys.readouterr().err


def test_antigravity_frontmatter_in_every_role():
    """Every rendered form uses Antigravity tool names and no Claude Code-only fields."""
    claude_tools = {"Read", "Write", "Edit", "Glob", "Grep", "Bash", "Agent", "AskUserQuestion", "Task"}
    for path, text in render_roles.render_all().items():
        if not path.endswith(".md") or ("/assets/" in path or "/references/" in path):
            continue
        fm = text.split("---", 2)[1]
        assert "\ntools:" in fm, path
        tools = {line.strip()[2:].strip() for line in fm.splitlines() if line.strip().startswith("- ")}
        assert tools and not tools & claude_tools, (path, tools & claude_tools)
        assert "\nmodel:" not in fm and "\ncolor:" not in fm, path
        if path.endswith("agent.md"):
            assert "\nsubagent: true" in fm, path
        body = text.split("---", 2)[2]
        for word in ("CLAUDE_PLUGIN_ROOT", "subagent_type", ".claude/", "Claude Code"):
            assert word not in body, (path, word)
