# packages/wal-core/src/wal_core/schema.py

import hashlib
from typing import Annotated, Optional, Union

from pydantic import AnyUrl, BaseModel, Field, FilePath, NonNegativeInt, StringConstraints, TypeAdapter, UrlConstraints

from wal_core.constants import StepMode

# Basic type definitions
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9-]*$")]
Reference = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9-]*(?:\.[A-Za-z][A-Za-z0-9-]*)*$")]

SHA256Hash = Annotated[str, StringConstraints(pattern=r"^[a-fA-F0-9]{64}$", min_length=64, max_length=64)]
SHA256HashAdapter = TypeAdapter(SHA256Hash)

# Type aliases
ImportPath = Union[FilePath, Annotated[AnyUrl, UrlConstraints(allowed_schemes=["http", "https"])]]
ImportPathAdapter = TypeAdapter(ImportPath)


class BaseLine(BaseModel):
    lineno: NonNegativeInt  # absolute line number in the file
    depth: NonNegativeInt = 0  # indent level (each level is 2 spaces)


class EmptyLine(BaseLine):
    pass


class CommentLine(BaseLine):
    text: str


class ImportLine(BaseLine):
    alias: Identifier
    path: ImportPath


class VariableLine(BaseLine):
    name: Identifier
    text: str


class StepLine(BaseLine):
    mode: StepMode
    tag: Optional[Identifier] = None
    jump: Optional[Reference] = None
    text: str


# Union of all possible line types
LineItem = Union[EmptyLine, CommentLine, ImportLine, VariableLine, StepLine]


class ReferenceNode(BaseModel):
    reference: Reference
    pipe: Optional[str]

    def fingerprint(self) -> SHA256Hash:
        content = self.reference
        if self.pipe is not None:
            content = f"{content}|{self.pipe}"
        return hashlib.sha256(content.encode()).hexdigest()


class WorkflowModule(BaseModel):
    path: ImportPath
    namespace: SHA256Hash
    line_map: dict[NonNegativeInt, LineItem] = Field(default_factory=dict)
    label_map: dict[Identifier, LineItem] = Field(default_factory=dict)
    ref_map: dict[SHA256Hash, ReferenceNode] = Field(default_factory=dict)
