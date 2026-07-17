import os
import re
from wf_model import parse_run
from wf_render import render_html, load_template

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "wf_c8873586-bae.json")


def test_charset_within_first_1024_bytes():
    html = load_template()
    assert 0 <= html.encode("utf-8").find(b'<meta charset="utf-8">') < 1024


def test_render_has_node_and_bar_per_agent_and_no_placeholders():
    r = parse_run(FIXTURE)
    html = render_html(r, load_template())
    assert html.count('class="agent ') == 13
    assert html.count('class="trow"') == 13
    # design §8: no unresolved {{TOKEN}} placeholders remain. The template's
    # minified CSS/JS legitimately contains adjacent `}}`, so match the token
    # pattern precisely instead of a blanket `}}` ban.
    assert not re.search(r"\{\{[A-Z_]+\}\}", html)
    assert r.workflow_name in html


def test_render_escapes_html():
    r = parse_run(FIXTURE)
    r.phases[0].agents[0].prompt_preview = "<script>alert(1)</script>"
    html = render_html(r, load_template())
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
