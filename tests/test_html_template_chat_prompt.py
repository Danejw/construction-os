"""Prompt smoke tests for HTML template injection in chat system prompts."""

from ai_prompter import Prompter


SAMPLE_HTML = """<!DOCTYPE html><html><body>
<p>Trade: <span id="trade">Carpentry</span></p>
</body></html>"""


def test_chat_system_prompt_includes_html_template_section():
    rendered = Prompter(prompt_template="chat/system").render(
        data={
            "html_template": {
                "id": "html_template:t1",
                "name": "KCDBC Bid",
                "category": "estimate",
                "html_body": SAMPLE_HTML,
            }
        }
    )
    assert "SELECTED HTML TEMPLATE (PARALLEL OUTPUT)" in rendered
    assert "KCDBC Bid" in rendered
    assert "estimate" in rendered
    assert "Do not paste, rewrite, or generate the HTML document yourself" in rendered
    assert "runtime will independently derive a strict schema" in rendered
    assert "attach the completed HTML document" in rendered


def test_chat_system_prompt_omits_html_template_when_absent():
    rendered = Prompter(prompt_template="chat/system").render(data={})
    assert "SELECTED HTML TEMPLATE (PARALLEL OUTPUT)" not in rendered
