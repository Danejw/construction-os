import pytest
from langchain_core.messages import HumanMessage

from construction_os.services import html_template_binding as binding
from construction_os.tool_runtime import chat_loop


def test_compile_contract_supports_unknown_template_shapes():
    contract = binding.compile_html_template_contract(
        """
        <html>
          <body>
            <h1>{{project.name}}</h1>
            <p data-bind="project_address">123 Main Street</p>
            <div><span>Old total</span></div>
            <p>Static project summary</p>
          </body>
        </html>
        """
    )

    kinds_and_targets = {(slot.kind, slot.target) for slot in contract.slots}

    assert ("placeholder", "project.name") in kinds_and_targets
    assert ("element", "project_address") in kinds_and_targets
    assert ("span", "1") in kinds_and_targets
    assert any(
        slot.kind == "leaf" and slot.current_value == "Static project summary"
        for slot in contract.slots
    )


def test_apply_bindings_preserves_structure_and_escapes_values():
    source = """
    <!doctype html>
    <html>
      <head><style>@page { size: A4; }</style></head>
      <body>
        <h1>{{project_name}}</h1>
        <p data-field="address">Old address</p>
        <span class="total">Old total</span>
        <img src="/api/media/logo/file" alt="Logo">
      </body>
    </html>
    """
    contract = binding.compile_html_template_contract(source)
    values = {}
    for slot in contract.slots:
        if slot.target == "project_name":
            values[slot.slot_id] = "GEN Korean BBQ"
        elif slot.target == "address":
            values[slot.slot_id] = "75-971 Henry Street"
        elif slot.kind == "span":
            values[slot.slot_id] = "<script>alert(1)</script>"
        else:
            values[slot.slot_id] = slot.current_value

    rendered = binding.apply_html_template_bindings(contract, values)

    assert "@page { size: A4; }" in rendered
    assert '<img src="/api/media/logo/file" alt="Logo">' in rendered
    assert "GEN Korean BBQ" in rendered
    assert "75-971 Henry Street" in rendered
    assert "<script>alert(1)</script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


def test_attach_rendered_html_replaces_model_generated_html():
    content = "Grounded result.\n\n```html\n<html>old</html>\n```"

    attached = binding.attach_rendered_html(content, "<html>new</html>")

    assert "Grounded result." in attached
    assert "<html>old</html>" not in attached
    assert attached.count("```html") == 1
    assert "<html>new</html>" in attached


def test_emit_html_template_output_dispatches_custom_event(monkeypatch):
    emitted = []

    def fake_dispatch(name, value, *, config):
        emitted.append((name, value, config))

    monkeypatch.setattr(chat_loop, "dispatch_custom_event", fake_dispatch)
    config = {"configurable": {"thread_id": "chat_session:test"}}

    did_emit = chat_loop.emit_html_template_output(
        message_id="ai-1",
        template_id="html_template:proposal",
        html="<html><body>Proposal</body></html>",
        config=config,
    )

    assert did_emit is True
    assert emitted == [
        (
            "html_template_output",
            {
                "messageId": "ai-1",
                "templateId": "html_template:proposal",
                "html": "<html><body>Proposal</body></html>",
            },
            config,
        )
    ]


@pytest.mark.asyncio
async def test_render_selected_template_uses_runtime_structured_schema(monkeypatch):
    class Template:
        html_body = (
            "<html><body><h1>{{project_name}}</h1>"
            '<p data-bind="address">Old address</p>'
            "<span>Old total</span></body></html>"
        )

    async def fake_get(_template_id):
        return Template()

    async def fake_expand(html_body):
        return html_body

    class FakeStructuredModel:
        def __init__(self, schema):
            self.schema = schema

        async def ainvoke(self, _messages, config=None):
            del config
            result = {}
            for slot_id, field in self.schema["properties"].items():
                description = field["description"]
                if "template field 'project_name'" in description:
                    result[slot_id] = "GEN Korean BBQ"
                elif "template field 'address'" in description:
                    result[slot_id] = "75-971 Henry Street"
                else:
                    result[slot_id] = "$2,200,000"
            return result

    class FakeModel:
        def with_structured_output(self, schema, method=None, **kwargs):
            del method, kwargs
            return FakeStructuredModel(schema)

        async def ainvoke(self, _messages, config=None):
            del config
            raise AssertionError("JSON fallback should not run")

    async def fake_provision(*_args, **_kwargs):
        return FakeModel()

    monkeypatch.setattr(binding.HtmlTemplate, "get", staticmethod(fake_get))
    monkeypatch.setattr(binding, "expand_image_tokens", fake_expand)

    rendered = await binding.render_selected_html_template(
        template_id="html_template:test",
        assistant_text="The project total is $2,200,000.",
        grounding_messages=[HumanMessage(content="Create the proposal.")],
        model_id=None,
        provision_model=fake_provision,
        config={},
    )

    assert "GEN Korean BBQ" in rendered
    assert "75-971 Henry Street" in rendered
    assert "$2,200,000" in rendered
    assert "{{project_name}}" not in rendered
