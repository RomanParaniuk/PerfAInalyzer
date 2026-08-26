"""The markdown-based stage registry: file discovery, frontmatter parsing, and the
byte-identical-system-prompt guarantee the prompt cache depends on (Principle II)."""

import pytest
from src.models.stage import STAGE_ORDER, StageName
from src.pipeline.stages import STAGE_FILES, get_stage_specs, parse_stage_file

SONNET_STAGES = [name for name in STAGE_ORDER if name is not StageName.STRUCTURAL_CONTEXT]


class TestGetStageSpecs:
    def test_returns_a_spec_for_every_stage(self):
        specs = get_stage_specs()
        assert set(specs) == set(STAGE_ORDER)
        for name, spec in specs.items():
            assert spec.name is name

    def test_instructions_are_nonempty_stage_task_bodies(self):
        for spec in get_stage_specs().values():
            assert spec.instructions.startswith("# Stage task:")
            assert spec.instructions.endswith("\n")

    def test_instructions_carry_no_frontmatter(self):
        for spec in get_stage_specs().values():
            assert "---" not in spec.instructions.splitlines()[0]

    def test_sonnet_stages_share_a_byte_identical_system_prompt(self):
        """Required for the shared prompt-cache prefix across Stages 2-4."""
        specs = get_stage_specs()
        prompts = {specs[name].system_prompt for name in SONNET_STAGES}
        assert len(prompts) == 1

    def test_structural_stage_has_its_own_system_prompt(self):
        specs = get_stage_specs()
        structural = specs[StageName.STRUCTURAL_CONTEXT].system_prompt
        assert structural != specs[StageName.ALGORITHMIC_COMPLEXITY].system_prompt
        assert '"structural_context"' in structural


class TestParseStageFile:
    def test_splits_frontmatter_and_body(self):
        meta, body = parse_stage_file(
            "---\nname: x\nsystem: y\n---\n# Stage task: t\nbody\n", "f.md"
        )
        assert meta == {"name": "x", "system": "y"}
        assert body == "# Stage task: t\nbody\n"

    def test_body_may_contain_horizontal_rules(self):
        _meta, body = parse_stage_file("---\nname: x\n---\nabove\n---\nbelow\n", "f.md")
        assert body == "above\n---\nbelow\n"

    def test_missing_frontmatter_is_rejected(self):
        with pytest.raises(ValueError, match="missing frontmatter"):
            parse_stage_file("# no frontmatter\n", "f.md")

    def test_unterminated_frontmatter_is_rejected(self):
        with pytest.raises(ValueError, match="unterminated frontmatter"):
            parse_stage_file("---\nname: x\n", "f.md")

    def test_malformed_frontmatter_line_is_rejected(self):
        with pytest.raises(ValueError, match="malformed frontmatter"):
            parse_stage_file("---\nnot a mapping\n---\nbody\n", "f.md")


class TestStageFilesOnDisk:
    def test_every_stage_file_declares_its_own_stage_name(self):
        from src.pipeline.stages import _read_text

        for stage, filename in STAGE_FILES.items():
            meta, _body = parse_stage_file(_read_text(filename), filename)
            assert meta["name"] == stage.value
