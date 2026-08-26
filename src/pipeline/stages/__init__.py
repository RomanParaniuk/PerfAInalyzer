"""Stage registry: each analysis stage is defined by a markdown file in this directory.

A stage file is `key: value` frontmatter (`name`: the StageName value; `system`: which
`system-<value>.md` file provides the system prompt) followed by the stage instructions
as its body. The markdown files are the single source of truth for both execution
paths: this loader serves the hosted CLI, and the plugin skill points subagents at the
same files.

Cache note (Principle II): the three Sonnet stages reference one system-prompt file
(`system-sonnet.md`), keeping their system prompt byte-identical — together with the
identical tool definition and the shared context block, that makes the prompt-cache
prefix identical across Stages 2-4. Stage-specific instructions ride *after* the cache
checkpoint, in the user turn.
"""

from __future__ import annotations

from importlib import resources

from src.models.stage import StageName
from src.pipeline.orchestrator import StageSpec

STAGE_FILES: dict[StageName, str] = {
    StageName.STRUCTURAL_CONTEXT: "structural.md",
    StageName.ALGORITHMIC_COMPLEXITY: "complexity.md",
    StageName.RESOURCE_IO_EFFICIENCY: "resource_io.md",
    StageName.CONCURRENCY_SCALABILITY: "concurrency.md",
}


def _read_text(filename: str) -> str:
    return (resources.files(__package__) / filename).read_text(encoding="utf-8")


def parse_stage_file(text: str, filename: str) -> tuple[dict[str, str], str]:
    """Split a stage markdown file into its frontmatter mapping and instruction body."""
    if not text.startswith("---\n"):
        raise ValueError(f"{filename}: missing frontmatter block")
    header, sep, body = text[4:].partition("\n---\n")
    if not sep:
        raise ValueError(f"{filename}: unterminated frontmatter block")
    meta: dict[str, str] = {}
    for line in header.splitlines():
        if not line.strip():
            continue
        key, colon, value = line.partition(":")
        if not colon:
            raise ValueError(f"{filename}: malformed frontmatter line {line!r}")
        meta[key.strip()] = value.strip()
    return meta, body.lstrip("\n")


def _load_spec(stage: StageName, filename: str) -> StageSpec:
    meta, instructions = parse_stage_file(_read_text(filename), filename)
    if meta.get("name") != stage.value:
        raise ValueError(
            f"{filename}: frontmatter name {meta.get('name')!r} does not match the "
            f"expected stage '{stage.value}'"
        )
    system = meta.get("system")
    if not system:
        raise ValueError(f"{filename}: frontmatter is missing the 'system' key")
    return StageSpec(
        name=stage,
        system_prompt=_read_text(f"system-{system}.md"),
        instructions=instructions,
    )


def get_stage_specs() -> dict[StageName, StageSpec]:
    return {stage: _load_spec(stage, filename) for stage, filename in STAGE_FILES.items()}
