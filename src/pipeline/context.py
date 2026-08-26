"""Local structural analysis: tree-sitter index, relevance ranking, and context assembly.

Everything in this module is zero-token local computation (Principle II): the structural
index is built once per run and reused by all four stages; each stage then receives only
its top-ranked, token-budget-capped excerpts plus one shared, byte-identical context
prefix that is prompt-cached across Stages 2–4.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from src.lib.discovery import SourceFile
from src.models.stage import StageName

logger = logging.getLogger("perf_ai.context")

# ~4 characters per token is a serviceable local estimate; budgets are deliberately
# conservative so the estimate erring low cannot overflow a real context window.
def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def estimate_tokens_chars(char_count: int) -> int:
    return max(1, char_count // 4)


# `claude-haiku-4-5` (structural stage) has a 200K context window; Sonnet stages have 1M
# available but budgets stay capped per Principle II. Budgets are estimated input tokens
# for shared context + stage excerpts combined.
HAIKU_CONTEXT_WINDOW_TOKENS = 200_000

DEFAULT_STAGE_INPUT_BUDGETS: dict[StageName, int] = {
    StageName.STRUCTURAL_CONTEXT: 24_000,
    StageName.ALGORITHMIC_COMPLEXITY: 40_000,
    StageName.RESOURCE_IO_EFFICIENCY: 40_000,
    StageName.CONCURRENCY_SCALABILITY: 40_000,
    StageName.MEMORY_ALLOCATION: 40_000,
    StageName.DATA_ACCESS_EFFICIENCY: 40_000,
    StageName.STARTUP_INITIALIZATION: 40_000,
}

assert DEFAULT_STAGE_INPUT_BUDGETS[StageName.STRUCTURAL_CONTEXT] < HAIKU_CONTEXT_WINDOW_TOKENS


@dataclass
class CodeChunk:
    """A contiguous slice of one source file (function/class body, or a fallback block)."""

    file: SourceFile
    symbol: str | None
    kind: str  # "function" | "class" | "block"
    line_start: int  # 1-indexed, inclusive
    line_end: int  # 1-indexed, inclusive
    text: str
    best_effort: bool = False  # True when produced by the fallback chunker


@dataclass
class FileIndex:
    file: SourceFile
    chunks: list[CodeChunk] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    has_syntax_errors: bool = False
    best_effort: bool = False  # no grammar available; fallback chunker used


@dataclass
class StructuralIndex:
    root: Path
    files: list[FileIndex] = field(default_factory=list)

    def all_chunks(self) -> list[CodeChunk]:
        return [chunk for f in self.files for chunk in f.chunks]

    def files_with_syntax_errors(self) -> list[str]:
        return [f.file.rel_path for f in self.files if f.has_syntax_errors]

    def best_effort_files(self) -> list[str]:
        return [f.file.rel_path for f in self.files if f.best_effort]

    def code_map_text(self, max_tokens: int | None = None) -> str:
        """Compact repository map sent to the model instead of raw source (Principle II).

        With `max_tokens`, per-file entries beyond the budget are dropped and replaced
        with an explicit truncation marker, so the map's size is bounded regardless of
        repository size (rather than silently outgrowing the stage budgets)."""
        lines: list[str] = ["# Repository code map", ""]
        used_chars = sum(len(line) + 1 for line in lines)
        included = 0
        for f in self.files:
            flags = []
            if f.best_effort:
                flags.append("no grammar available; best-effort chunking")
            if f.has_syntax_errors:
                flags.append("contains syntax errors; partial parse")
            flag_text = f"  [{'; '.join(flags)}]" if flags else ""
            entry = [f"## {f.file.rel_path} ({f.file.language}){flag_text}"]
            if f.imports:
                entry.append(f"imports: {', '.join(f.imports[:20])}")
            for chunk in f.chunks:
                if chunk.symbol:
                    entry.append(
                        f"- {chunk.kind} {chunk.symbol} (lines {chunk.line_start}-{chunk.line_end})"
                    )
            entry.append("")
            entry_text = "\n".join(entry)
            entry_chars = len(entry_text) + 1
            if max_tokens is not None and estimate_tokens_chars(used_chars + entry_chars) > max_tokens:
                omitted = len(self.files) - included
                lines.append(
                    f"(map truncated to fit the token budget: {omitted} of "
                    f"{len(self.files)} files are not listed above)"
                )
                break
            lines.append(entry_text)
            used_chars += entry_chars
            included += 1
        return "\n".join(lines)


# Definition-like node types across common tree-sitter grammars. Walk does not descend
# into a matched node, so chunks stay disjoint.
DEF_NODE_TYPES = frozenset(
    {
        "function_definition",
        "function_declaration",
        "function_item",
        "method_definition",
        "method_declaration",
        "constructor_declaration",
        "class_definition",
        "class_declaration",
        "class_specifier",
        "interface_declaration",
        "impl_item",
        "struct_item",
        "trait_item",
        "method",
        "singleton_method",
        "module",
        "generator_function_declaration",
    }
)

CLASS_KIND_TYPES = frozenset(
    {
        "class_definition",
        "class_declaration",
        "class_specifier",
        "interface_declaration",
        "impl_item",
        "struct_item",
        "trait_item",
        "module",
    }
)

IMPORT_NODE_TYPES = frozenset(
    {
        "import_statement",
        "import_from_statement",
        "import_declaration",
        "import_header",
        "use_declaration",
        "preproc_include",
        "require",
        "using_directive",
    }
)

# Fallback chunker tuning.
FALLBACK_MAX_CHUNK_LINES = 120
FALLBACK_MIN_CHUNK_LINES = 20


@lru_cache(maxsize=64)
def _get_parser(language: str):
    """Resolve a tree-sitter parser for `language`, or None when no grammar is available."""
    try:
        from tree_sitter_language_pack import get_parser

        return get_parser(language)  # type: ignore[arg-type]
    except Exception:
        return None


def _node_symbol(node) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is not None and name_node.text is not None:
        return name_node.text.decode("utf-8", errors="replace")
    return None


def _collect_definitions(node, out: list, imports: list[str], source: bytes) -> None:
    for child in node.children:
        if child.type in IMPORT_NODE_TYPES:
            text = source[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
            imports.append(" ".join(text.split())[:120])
            continue
        if child.type in DEF_NODE_TYPES:
            out.append(child)
            continue  # do not descend: keep chunks disjoint
        _collect_definitions(child, out, imports, source)


def _chunk_from_lines(
    file: SourceFile, lines: Sequence[str], start: int, end: int, *,
    symbol: str | None, kind: str, best_effort: bool,
) -> CodeChunk:
    return CodeChunk(
        file=file,
        symbol=symbol,
        kind=kind,
        line_start=start,
        line_end=end,
        text="\n".join(lines[start - 1 : end]),
        best_effort=best_effort,
    )


def fallback_chunk_file(file: SourceFile, text: str) -> list[CodeChunk]:
    """Generic line/indentation chunker for languages without an available grammar.

    Starts a new chunk at unindented, non-blank lines once the current chunk has grown
    past a minimum size, and hard-splits chunks past a maximum size.
    """
    lines = text.splitlines()
    if not lines:
        return []
    chunks: list[CodeChunk] = []
    start = 1
    for i, line in enumerate(lines[1:], start=2):
        current_len = i - start
        boundary = line.strip() and not line[0].isspace() and current_len >= FALLBACK_MIN_CHUNK_LINES
        if boundary or current_len >= FALLBACK_MAX_CHUNK_LINES:
            chunks.append(
                _chunk_from_lines(
                    file, lines, start, i - 1, symbol=None, kind="block", best_effort=True
                )
            )
            start = i
    chunks.append(
        _chunk_from_lines(file, lines, start, len(lines), symbol=None, kind="block", best_effort=True)
    )
    return chunks


def index_file(file: SourceFile) -> FileIndex:
    try:
        text = file.path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("could not read %s: %s", file.rel_path, exc)
        return FileIndex(file=file, has_syntax_errors=True, best_effort=True)

    parser = _get_parser(file.language)
    if parser is None:
        return FileIndex(file=file, chunks=fallback_chunk_file(file, text), best_effort=True)

    source = text.encode("utf-8")
    try:
        tree = parser.parse(source)
    except Exception as exc:
        logger.warning("tree-sitter parse failed for %s: %s", file.rel_path, exc)
        return FileIndex(file=file, chunks=fallback_chunk_file(file, text), best_effort=True)

    def_nodes: list = []
    imports: list[str] = []
    _collect_definitions(tree.root_node, def_nodes, imports, source)

    lines = text.splitlines()
    chunks: list[CodeChunk] = []
    for node in def_nodes:
        start_line = node.start_point[0] + 1
        end_line = min(node.end_point[0] + 1, len(lines))
        kind = "class" if node.type in CLASS_KIND_TYPES else "function"
        chunks.append(
            _chunk_from_lines(
                file, lines, start_line, end_line,
                symbol=_node_symbol(node), kind=kind, best_effort=False,
            )
        )
    if not chunks and lines:
        # Script-style file with no recognizable definitions: fall back to blocks.
        chunks = fallback_chunk_file(file, text)

    return FileIndex(
        file=file,
        chunks=chunks,
        imports=imports,
        has_syntax_errors=bool(tree.root_node.has_error),
    )


def build_structural_index(root: Path, files: Sequence[SourceFile]) -> StructuralIndex:
    return StructuralIndex(root=root, files=[index_file(f) for f in files])


# ---------------------------------------------------------------------------
# Stage-specific relevance ranking (research.md §4 heuristics)
# ---------------------------------------------------------------------------

_LOOP_RE = re.compile(r"^\s*(?:for\b|while\b|loop\b|\}?\s*else\s+for\b|.*\bforEach\()", re.MULTILINE)

_STAGE_PATTERNS: dict[StageName, list[tuple[re.Pattern[str], float]]] = {
    StageName.ALGORITHMIC_COMPLEXITY: [
        (re.compile(r"\b(?:for|while)\b"), 1.5),
        (re.compile(r"\.(?:append|push|insert|extend|add)\("), 1.5),
        (re.compile(r"\+="), 0.5),
        (re.compile(r"\bsorted?\("), 1.0),
        (re.compile(r"\bin\s+\w+"), 0.5),
        (re.compile(r"\.(?:index|count|find|indexOf|includes)\("), 1.0),
    ],
    StageName.RESOURCE_IO_EFFICIENCY: [
        (re.compile(r"\bopen\(|\bread\w*\(|\bwrite\w*\("), 2.0),
        (re.compile(r"\b(?:requests|urllib|httpx|fetch|axios|http)\b"), 2.0),
        (re.compile(r"\b(?:socket|connect)\b"), 1.5),
        (re.compile(r"\b(?:execute|executemany|cursor|query)\b|\bSELECT\b|\bINSERT\b|\bUPDATE\b", re.IGNORECASE), 2.0),
        (re.compile(r"\b(?:subprocess|os\.system|popen)\b", re.IGNORECASE), 1.5),
        (re.compile(r"\b(?:json|pickle|csv|yaml)\.(?:load|dump)"), 1.0),
        (re.compile(r"\bos\.(?:listdir|walk|scandir|stat)\b|\bglob\b"), 1.0),
    ],
    StageName.CONCURRENCY_SCALABILITY: [
        (re.compile(r"\b(?:threading|Thread|thread)\b"), 2.0),
        (re.compile(r"\b(?:Lock|RLock|mutex|Mutex|Semaphore|semaphore|Condition)\b"), 2.0),
        (re.compile(r"\basync\b|\bawait\b|\basyncio\b"), 1.5),
        (re.compile(r"\b(?:multiprocessing|Pool|ProcessPool|ThreadPool|Executor)\b"), 2.0),
        (re.compile(r"\b(?:synchronized|volatile|atomic|Atomic)\b"), 2.0),
        (re.compile(r"\b(?:goroutine|go\s+func|chan\b|channel)\b"), 2.0),
        (re.compile(r"\b(?:queue|Queue|deque)\b"), 1.0),
    ],
    StageName.MEMORY_ALLOCATION: [
        (re.compile(r"\bdeepcopy\b|\.copy\(|\bclone\("), 2.0),
        (re.compile(r"\b(?:cache|Cache|memo)\w*\b"), 1.5),
        (re.compile(r"\.(?:append|push|extend|add|insert)\("), 1.0),
        (re.compile(r"\+=\s*['\"]|\+\s*['\"]"), 1.5),
        (re.compile(r"\b(?:global|weakref|__del__|gc)\b"), 1.5),
        (re.compile(r"\b(?:addEventListener|removeEventListener|subscribe|unsubscribe|on|off)\("), 1.0),
        (re.compile(r"\b(?:StringIO|BytesIO|StringBuilder|bytearray)\b"), 1.0),
        (re.compile(r"\breadlines?\(\)|\.to_list\(|\btolist\(|\blist\("), 1.0),
    ],
    StageName.DATA_ACCESS_EFFICIENCY: [
        (re.compile(r"\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bJOIN\b", re.IGNORECASE), 2.0),
        (re.compile(r"\b(?:execute|executemany|cursor|fetchall|fetchone|fetchmany)\b"), 2.0),
        (re.compile(r"\b(?:session|objects|query|queryset|findOne|findMany|findAll|aggregate)\b"), 1.5),
        (re.compile(r"\b(?:sqlalchemy|django\.db|prisma|typeorm|sequelize|knex|mongoose|pymongo|redis)\b", re.IGNORECASE), 2.0),
        (re.compile(r"\b(?:commit|rollback|transaction|savepoint)\b"), 1.5),
        (re.compile(r"\b(?:select_related|prefetch_related|joinedload|selectinload|eager)\b"), 2.0),
        (re.compile(r"\bLIMIT\b|\bOFFSET\b|\bpaginat\w+\b", re.IGNORECASE), 1.0),
        (re.compile(r"\b(?:ForeignKey|relationship|belongs_to|has_many|hasMany)\b"), 1.0),
    ],
    StageName.STARTUP_INITIALIZATION: [
        (re.compile(r"__main__|\bdef main\b|\bfunc main\b|if __name__"), 2.0),
        (re.compile(r"\b(?:init|setup|bootstrap|configure|startup)\w*\s*\("), 1.5),
        (re.compile(r"\bre\.compile\(|\bcompile\("), 1.0),
        (re.compile(r"\b(?:getenv|environ|dotenv|load_dotenv|ConfigParser|from_envvar)\b"), 1.5),
        (re.compile(r"\b(?:load_model|load_config|read_config|load_settings|parse_config)\b"), 2.0),
        (re.compile(r"\b(?:json|yaml|toml|pickle)\.(?:load|safe_load|loads)\("), 1.0),
        (re.compile(r"\b(?:import_module|__import__|require)\("), 1.5),
    ],
    StageName.STRUCTURAL_CONTEXT: [],  # handled by _structural_score
}

_ENTRYPOINT_NAME_RE = re.compile(r"(?:^|/)(?:main|app|index|cli|server|__init__|__main__)\.\w+$")


def loop_nesting_depth(text: str) -> int:
    """Approximate maximum loop-nesting depth using indentation of loop lines.

    Works as a heuristic across indentation- and brace-style languages alike.
    """
    depth = 0
    stack: list[int] = []  # indents of enclosing loop lines
    for line in text.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        while stack and indent <= stack[-1]:
            stack.pop()
        if _LOOP_RE.match(line):
            stack.append(indent)
            depth = max(depth, len(stack))
    return depth


def _structural_score(chunk: CodeChunk, file_index: FileIndex) -> float:
    """The structural stage prefers breadth: entry points, import-heavy files, classes."""
    score = 1.0  # every chunk is somewhat relevant to a structural overview
    if _ENTRYPOINT_NAME_RE.search(chunk.file.rel_path):
        score += 3.0
    score += min(len(file_index.imports), 10) * 0.3
    if chunk.kind == "class":
        score += 1.0
    return score


def score_chunk(chunk: CodeChunk, stage: StageName, file_index: FileIndex) -> float:
    if stage is StageName.STRUCTURAL_CONTEXT:
        return _structural_score(chunk, file_index)
    score = 0.0
    for pattern, weight in _STAGE_PATTERNS[stage]:
        score += weight * len(pattern.findall(chunk.text))
    if stage is StageName.ALGORITHMIC_COMPLEXITY:
        depth = loop_nesting_depth(chunk.text)
        if depth >= 2:
            score += depth * 5.0
        if chunk.symbol and re.search(rf"\b{re.escape(chunk.symbol)}\s*\(", chunk.text[chunk.text.find("\n") + 1 :]):
            score += 2.0  # likely recursion
    if stage is StageName.STARTUP_INITIALIZATION:
        # Startup cost concentrates in entry points and module-level code.
        if _ENTRYPOINT_NAME_RE.search(chunk.file.rel_path):
            score += 3.0
        score += min(len(file_index.imports), 10) * 0.2
    return score


def rank_chunks(index: StructuralIndex, stage: StageName) -> list[tuple[float, CodeChunk]]:
    """All chunks scored for `stage`, highest first; ties broken by file path/line."""
    scored: list[tuple[float, CodeChunk]] = []
    for file_index in index.files:
        for chunk in file_index.chunks:
            scored.append((score_chunk(chunk, stage, file_index), chunk))
    scored.sort(key=lambda pair: (-pair[0], pair[1].file.rel_path, pair[1].line_start))
    return scored


# ---------------------------------------------------------------------------
# Prompt-cache context assembly
# ---------------------------------------------------------------------------


@dataclass
class ContextBundle:
    """Assembled model input for one stage call."""

    shared_context: str  # byte-identical across Stages 2-4 (prompt-cache prefix)
    stage_excerpts: str  # stage-specific ranked excerpts within the token budget
    coverage_note: str | None  # what was left out, when the budget truncated


# The shared code map may consume at most half of the smallest stage budget, so every
# stage always retains room for its own ranked excerpts regardless of repository size.
DEFAULT_MAP_TOKEN_CAP = min(DEFAULT_STAGE_INPUT_BUDGETS.values()) // 2


def build_shared_context(
    index: StructuralIndex,
    stage1_summary: str | None = None,
    *,
    max_map_tokens: int | None = DEFAULT_MAP_TOKEN_CAP,
) -> str:
    """The shared prefix for Stages 2-4: local code map + Stage 1's architectural summary.

    Built exactly once per run so the string is byte-identical across the three Sonnet
    stages — a requirement for the prompt cache to hit (Principle II). The map portion
    is token-capped so the shared prefix can never crowd out stage excerpts (or, for
    the structural stage, overflow `claude-haiku-4-5`'s context window)."""
    parts = [index.code_map_text(max_tokens=max_map_tokens)]
    if stage1_summary:
        parts.append("# Architectural summary (from the structural analysis stage)\n")
        parts.append(stage1_summary)
    return "\n".join(parts)


def _format_excerpt(chunk: CodeChunk) -> str:
    symbol = f" {chunk.symbol}" if chunk.symbol else ""
    flag = " [best-effort chunk: no grammar for this language]" if chunk.best_effort else ""
    return (
        f"### {chunk.file.rel_path}:{chunk.line_start}-{chunk.line_end}"
        f" ({chunk.kind}{symbol}, {chunk.file.language}){flag}\n"
        f"```\n{chunk.text}\n```\n"
    )


def assemble_context(
    index: StructuralIndex,
    stage: StageName,
    *,
    shared_context: str,
    token_budget: int | None = None,
) -> ContextBundle:
    """Pick top-ranked excerpts for `stage` until the input token budget is exhausted."""
    budget = token_budget if token_budget is not None else DEFAULT_STAGE_INPUT_BUDGETS[stage]
    if stage is StageName.STRUCTURAL_CONTEXT:
        budget = min(budget, HAIKU_CONTEXT_WINDOW_TOKENS // 2)

    remaining = budget - estimate_tokens(shared_context)
    ranked = rank_chunks(index, stage)
    relevant = [(score, chunk) for score, chunk in ranked if score > 0]

    excerpts: list[str] = []
    included_chunks: list[CodeChunk] = []
    omitted_chunks: list[CodeChunk] = []
    for _score, chunk in relevant:
        excerpt = _format_excerpt(chunk)
        cost = estimate_tokens(excerpt)
        if cost > remaining:
            omitted_chunks.append(chunk)
            continue
        excerpts.append(excerpt)
        remaining -= cost
        included_chunks.append(chunk)

    coverage_note: str | None = None
    if omitted_chunks:
        included_files = {chunk.file.rel_path for chunk in included_chunks}
        omitted_files = sorted(
            {chunk.file.rel_path for chunk in omitted_chunks} - included_files
        )
        coverage_note = (
            f"Token budget capped this stage's input: {len(included_chunks)} of {len(relevant)} "
            f"relevant code chunks were included. Files not fully covered: "
            f"{', '.join(omitted_files) if omitted_files else 'portions of the included files'}."
        )

    return ContextBundle(
        shared_context=shared_context,
        stage_excerpts="\n".join(excerpts) if excerpts else "(no stage-specific excerpts selected)",
        coverage_note=coverage_note,
    )
