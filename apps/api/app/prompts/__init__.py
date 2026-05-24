from __future__ import annotations

from pathlib import Path
from string import Formatter


class PromptRenderer:
    def __init__(self, prompts_dir: Path | None = None) -> None:
        self.prompts_dir = prompts_dir or Path(__file__).resolve().parent

    def render(self, template_name: str, **kwargs: object) -> str:
        path = self.prompts_dir / template_name
        if not path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_name}")

        template = path.read_text(encoding="utf-8")
        required_fields = {
            field_name
            for _, field_name, _, _ in Formatter().parse(template)
            if field_name
        }
        missing = sorted(required_fields.difference(kwargs))
        if missing:
            raise KeyError(f"Missing prompt value(s): {', '.join(missing)}")
        return template.format(**kwargs)
