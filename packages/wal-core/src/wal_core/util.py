# packages/wal-core/src/wal_core/util.py

import re

from pydantic import NonNegativeInt

from wal_core.constants import (
    INDENT_UNIT,
    PREFIX_COMMENT,
    PREFIX_IMPORT,
    PREFIX_STEP,
    PREFIX_VARIABLE,
    SUBSTITUTION_END,
    SUBSTITUTION_PIPE,
    SUBSTITUTION_START,
    SYMBOL_AT,
    SYMBOL_EQUALS,
    SYMBOL_QUESTION,
    SYMBOL_SHELL,
    TAG_CLOSE,
    TAG_OPEN,
    StepMode,
)
from wal_core.schema import (
    CommentLine,
    EmptyLine,
    ImportLine,
    ImportPathAdapter,
    LineItem,
    ReferenceNode,
    SHA256Hash,
    StepLine,
    VariableLine,
    WorkflowModule,
)


def parse_line(context: WorkflowModule, line: str, lineno: NonNegativeInt) -> LineItem:
    stripped = line.rstrip()

    if not stripped:
        data = EmptyLine(lineno=lineno)
        add_context_line(context, data)
        return data

    depth = 0
    while stripped.startswith(INDENT_UNIT * (depth + 1)):
        depth += 1
    content = stripped.lstrip()

    # Use match statement for prefix pattern matching
    match content:
        case c if c.startswith(PREFIX_COMMENT):
            clean_content = c[len(PREFIX_COMMENT) :].strip()
            data = parse_comment(clean_content, lineno, depth)
            add_context_line(context, data)
            return data

        case c if c.startswith(PREFIX_IMPORT):
            if depth > 0:
                raise ValueError("Import lines must be at top level")
            clean_content = c[len(PREFIX_IMPORT) :].strip()
            data = parse_import(clean_content, lineno)
            add_context_line(context, data)
            return data

        case c if c.startswith(PREFIX_VARIABLE):
            if depth > 0:
                raise ValueError("Variable lines must be at top level")
            clean_content = c[len(PREFIX_VARIABLE) :].strip()
            data = parse_variable(clean_content, lineno)
            data.text = parse_substitution(context, data.text, lineno)
            add_context_line(context, data)
            return data

        case c if c.startswith(PREFIX_STEP):
            clean_content = c[len(PREFIX_STEP) :].strip()
            data = parse_step(clean_content, lineno, depth)
            data.text = parse_substitution(context, data.text, lineno)
            add_context_line(context, data)
            return data

        case _:
            raise ValueError(
                f"at {lineno} prefix not found"
                f", prefix should include ['{PREFIX_COMMENT}', '{PREFIX_IMPORT}', '{PREFIX_VARIABLE}', '{PREFIX_STEP}']"
            )


def add_context_line(context: WorkflowModule, line: LineItem):
    context.line_map[line.lineno] = line

    match line:
        case ImportLine():
            if line.alias in context.label_map:
                raise ValueError(f"Duplicate import alias '{line.alias}' at line {context.path}:{line.lineno}")
            context.label_map[line.alias] = line

        case VariableLine():
            context.label_map[line.name] = line

        case StepLine() if line.tag is not None:
            if line.tag in context.label_map:
                raise ValueError(f"Duplicate step tag '{line.tag}' at line {context.path}:{line.lineno}")
            context.label_map[line.tag] = line

        case _:
            pass


def parse_comment(line: str, lineno: NonNegativeInt, depth: NonNegativeInt) -> CommentLine:
    return CommentLine(lineno=lineno, depth=depth, text=line)


def parse_import(line: str, lineno: NonNegativeInt) -> ImportLine:
    if not line.startswith(TAG_OPEN):
        raise ValueError(f"at {lineno} import line must start with '{TAG_OPEN}'")

    close_paren = line.find(TAG_CLOSE)
    if close_paren == -1:
        raise ValueError(f"at {lineno} import line must end with '{TAG_CLOSE}'")

    alias = line[1:close_paren].strip()
    text = line[close_paren + 1 :].strip()
    path = ImportPathAdapter.validate_python(text)

    return ImportLine(alias=alias, path=path, lineno=lineno)


def parse_variable(line: str, lineno: NonNegativeInt) -> VariableLine:
    if SYMBOL_EQUALS not in line:
        raise ValueError(f"at {lineno} variable line must contain '{SYMBOL_EQUALS}'")

    parts = line.split(SYMBOL_EQUALS, 1)
    if len(parts) != 2:
        raise ValueError(f"at {lineno} variable line, parts should be 2, got {len(parts)}")

    name = parts[0].strip()
    text = parts[1].strip()

    return VariableLine(name=name, text=text, lineno=lineno)


def parse_step(line: str, lineno: NonNegativeInt, depth: NonNegativeInt) -> StepLine:
    # Initialize default values
    tag = None
    jump = None
    mode = StepMode.PLAIN
    text = line

    # Parse optional tag: (identifier)
    if line.startswith(TAG_OPEN):
        close_paren = line.find(TAG_CLOSE)
        if close_paren == -1:
            raise ValueError(f"at {lineno} step tag missing closing '{TAG_CLOSE}': {line}")

        tag = line[1:close_paren].strip()
        text = line[close_paren + 1 :].strip()

    # Parse optional control prefix
    if text.startswith(SYMBOL_AT):
        # Jump format: @reference! or @reference?
        if len(text) < 2:
            raise ValueError(f"at {lineno} invalid jump reference")

        # Find the control symbol (! or ?)
        exclamation_pos = text.find(SYMBOL_SHELL)
        question_pos = text.find(SYMBOL_QUESTION)

        match (exclamation_pos, question_pos):
            case (excl, ques) if excl != -1 and (ques == -1 or excl < ques):
                jump = text[1:excl].strip()
                mode = StepMode.SHELL
                text = text[excl + 1 :].strip()
            case (excl, ques) if ques != -1 and (excl == -1 or ques < excl):
                jump = text[1:ques].strip()
                mode = StepMode.QUESTION
                text = text[ques + 1 :].strip()
            case _:
                raise ValueError(f"at {lineno} jump reference must end with '{SYMBOL_SHELL}' or '{SYMBOL_QUESTION}'")

    elif text.startswith(SYMBOL_SHELL):
        # Direct shell command
        mode = StepMode.SHELL
        text = text[1:].strip()

    elif text.startswith(SYMBOL_QUESTION):
        # Direct question
        mode = StepMode.QUESTION
        text = text[1:].strip()

    return StepLine(lineno=lineno, depth=depth, mode=mode, tag=tag, jump=jump, text=text)


def parse_substitution(context: WorkflowModule, text: str, lineno: NonNegativeInt):
    cleaned_text = text
    offset = 0

    while True:
        start_pos = cleaned_text.find(SUBSTITUTION_START, offset)
        if start_pos == -1:
            break

        end_pos = cleaned_text.find(SUBSTITUTION_END, start_pos)
        if end_pos == -1:
            raise ValueError(f"at {lineno} substitution missing closing '{SUBSTITUTION_END}'")

        # Extract content between ${ and }
        raw = cleaned_text[start_pos + len(SUBSTITUTION_START) : end_pos]

        # Parse reference and optional pipe command
        pipe_pos = raw.find(SUBSTITUTION_PIPE)
        if pipe_pos != -1:
            reference = raw[:pipe_pos].strip()
            pipe_command = raw[pipe_pos + 1 :].strip()
        else:
            reference = raw.strip()
            pipe_command = None

        # Create ReferenceNode
        ref_node = ReferenceNode(reference=reference, pipe=pipe_command)
        ref_hash = ref_node.fingerprint()
        context.ref_map[ref_hash] = ref_node

        # Replace with placeholder (using hash for uniqueness)
        placeholder = get_ref_placeholder(ref_hash)
        cleaned_text = cleaned_text[:start_pos] + placeholder + cleaned_text[end_pos + 1 :]
        offset = start_pos + len(placeholder)

    return cleaned_text


def get_ref_placeholder(ref_hash: SHA256Hash) -> str:
    return f"__SUBST_{ref_hash}__"


SUBSTITUTION_PATTERN = r"__SUBST_([a-fA-F0-9]{64})__"
SUBSTITUTION_RE = re.compile(SUBSTITUTION_PATTERN)


def get_text_ref_hash(text: str) -> set[SHA256Hash]:
    return set(SUBSTITUTION_RE.findall(text))


def build_block_from_step(context: WorkflowModule, step: StepLine) -> list[StepLine]:
    block: list[StepLine] = [step]
    start_lineno = step.lineno
    start_depth = step.depth

    for lineno in sorted(context.line_map.keys()):
        if lineno <= start_lineno:
            continue
        line = context.line_map[lineno]
        if not isinstance(line, StepLine):
            continue
        if line.depth > start_depth:
            block.append(line)
        else:
            break
    return block


def build_root_block(context: WorkflowModule) -> list[StepLine]:
    root_steps = [
        line
        for lineno in sorted(context.line_map.keys())
        if isinstance(line := context.line_map[lineno], StepLine) and line.depth == 0
    ]
    full_block: list[StepLine] = []
    for step in root_steps:
        full_block.extend(build_block_from_step(context, step))
    return full_block
