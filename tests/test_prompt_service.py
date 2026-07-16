"""Tests for PromptService: rendering, StrictUndefined, list_templates."""

from __future__ import annotations

import json
from pathlib import Path

import jinja2
import pytest

from app.core.prompt_service import PromptService

_EXAMPLES_DIR = Path(__file__).parent.parent / "app" / "core" / "prompts" / "examples"
_PROMPTS_DIR = Path(__file__).parent.parent / "app" / "core" / "prompts"

# Templates that have a paired example JSON
_TEMPLATED_EXAMPLES = [
    ("scenario_extraction.j2", "scenario_extraction.example.json"),
    ("doc_summary.j2", "doc_summary.example.json"),
    ("next_steps.j2", "next_steps.example.json"),
    ("safety_classification.j2", "safety_classification.example.json"),
]


@pytest.fixture
def svc() -> PromptService:
    return PromptService()


@pytest.mark.parametrize("template_name,example_file", _TEMPLATED_EXAMPLES)
def test_render_with_example_produces_nonempty_output(
    svc: PromptService, template_name: str, example_file: str
) -> None:
    context = json.loads((_EXAMPLES_DIR / example_file).read_text())
    result = svc.render(template_name, context)
    assert result.strip(), f"{template_name} rendered to empty string"


def test_render_compress_history(svc: PromptService) -> None:
    result = svc.render(
        "compress_history.j2",
        {
            "older_messages": [
                {"role": "user", "content": "I was charged $35."},
                {"role": "assistant", "content": "That sounds like an overdraft fee."},
            ],
            "current_user_query": "Can I get a refund?",
        },
    )
    assert result.strip()
    assert "older_messages" not in result  # variable name must not leak into output


def test_strict_undefined_raises_on_missing_variable(svc: PromptService) -> None:
    with pytest.raises(jinja2.UndefinedError):
        svc.render("scenario_extraction.j2", {})  # user_query is missing


def test_template_not_found_raises(svc: PromptService) -> None:
    with pytest.raises(jinja2.TemplateNotFound):
        svc.render("nonexistent_template.j2", {})


def test_list_templates_includes_all_expected(svc: PromptService) -> None:
    templates = svc.list_templates()
    expected = {
        "scenario_extraction.j2",
        "scenario_extraction.simplified.j2",
        "doc_summary.j2",
        "next_steps.j2",
        "safety_classification.j2",
        "compress_history.j2",
    }
    assert expected.issubset(set(templates)), (
        f"Missing templates: {expected - set(templates)}"
    )


def test_structured_prompts_end_with_output_json_only(svc: PromptService) -> None:
    """Norm: every structured-output prompt ends with 'Output JSON only.'"""
    for tmpl_name in ("scenario_extraction.j2", "safety_classification.j2"):
        ctx = json.loads((_EXAMPLES_DIR / f"{tmpl_name.replace('.j2', '')}.example.json").read_text())
        rendered = svc.render(tmpl_name, ctx)
        assert "Output JSON only." in rendered, (
            f"{tmpl_name} does not contain 'Output JSON only.'"
        )
