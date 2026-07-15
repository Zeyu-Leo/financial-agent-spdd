"""Jinja2-backed prompt template loader.

Single entry point for all LLM prompt rendering. Templates live in
``app/core/prompts/`` and use the ``.j2`` extension. Strict-undefined
mode means a missing variable raises immediately at render time rather
than silently emitting an empty string.

Safeguard: this module never reads ``Settings`` or touches the network.
Templates receive a plain ``dict[str, Any]``; callers own the context.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import jinja2

# Default template directory — relative to this file's package root.
_DEFAULT_PROMPTS_DIR = Path(__file__).parent / "prompts"


class PromptService:
    """Load and render Jinja2 templates with strict-undefined enforcement.

    Parameters
    ----------
    template_dir:
        Directory that contains ``.j2`` files. Defaults to
        ``app/core/prompts/``. Tests may override this to point at a
        fixture directory.
    """

    def __init__(self, template_dir: Path = _DEFAULT_PROMPTS_DIR) -> None:
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_dir)),
            undefined=jinja2.StrictUndefined,
            # Trim the first newline after a block tag so templates render
            # cleanly without leading blank lines.
            trim_blocks=True,
            lstrip_blocks=True,
            # Keep newlines at end of file to avoid accidental truncation.
            keep_trailing_newline=True,
        )
        # Tiny LRU cache: template objects are parsed once and reused.
        self._get_template = lru_cache(maxsize=64)(self._env.get_template)

    def render(self, name: str, context: dict[str, Any]) -> str:
        """Render template *name* with *context* and return the result.

        Parameters
        ----------
        name:
            Template filename relative to ``template_dir``, e.g.
            ``"scenario_extraction.j2"``.
        context:
            Flat mapping of variable names to values. Every variable
            referenced in the template must be present; missing keys
            raise ``jinja2.UndefinedError`` (StrictUndefined).

        Raises
        ------
        jinja2.TemplateNotFound
            When *name* does not exist in the template directory.
        jinja2.UndefinedError
            When *context* is missing a variable the template references.
        """
        try:
            tmpl = self._get_template(name)
        except jinja2.TemplateNotFound as err:
            raise jinja2.TemplateNotFound(name, message=f"Prompt template not found: {name!r}") from err
        return tmpl.render(**context)

    def list_templates(self) -> list[str]:
        """Return sorted list of available ``.j2`` template names."""
        return sorted(self._env.list_templates(extensions=["j2"]))
