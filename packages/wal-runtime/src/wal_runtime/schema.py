# packages/wal-runtime/src/wal_runtime/schema.py


import traceback
from enum import Enum
from datetime import datetime
from typing import Literal, TypeVar, Any, Optional, Union
from typing_extensions import Annotated

from pydantic import BaseModel, Field, NonNegativeInt, PlainSerializer

from wal_core.schema import Identifier, ImportPath, SHA256Hash, StepLine, WorkflowModule


class ErrorInfo(BaseModel):
    exception_type: str
    message: str
    traceback: Optional[str] = None
    context: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_exception(cls, e: Exception, include_traceback: bool = True):
        return cls(
            exception_type=type(e).__name__,
            message=str(e),
            traceback=traceback.format_exc() if include_traceback else None,
        )


SerializableException = Annotated[
    Exception, PlainSerializer(lambda e: ErrorInfo.from_exception(e).model_dump(), return_type=dict)
]


class Environment(BaseModel):
    context: WorkflowModule
    import_map: dict[Identifier, "Environment"] = Field(default_factory=dict)
    variable_map: dict[Identifier, str] = Field(default_factory=dict)
    step_output_map: dict[Identifier, str] = Field(default_factory=dict)


class Frame(BaseModel):
    environment: Environment
    block: list[StepLine]
    pc: NonNegativeInt


class StepRecord(BaseModel):
    step: StepLine
    pc: NonNegativeInt
    module_path: ImportPath
    module_hash: SHA256Hash
    resolved_text: str
    result_text: str
    success: bool


class RunStatus(str, Enum):
    TODO = "todo"
    EXEC = "exec"
    DONE = "done"
    FAIL = "fail"


class RunMeta(BaseModel):
    run_id: SHA256Hash
    module_path: ImportPath
    module_hash: SHA256Hash
    status: RunStatus = Field(default=RunStatus.TODO)
    created_at: datetime = Field(default_factory=datetime.now)


T_RunMeta = TypeVar("T_RunMeta", bound=RunMeta)


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    STEP_COMPLETED = "step_completed"
    RUN_FINISHED = "run_finished"


class RunEventBase(BaseModel):
    pass


class RunStartedEvent(RunEventBase):
    event_type: Literal[EventType.RUN_STARTED] = EventType.RUN_STARTED
    run_meta: RunMeta


class StepCompletedEvent(RunEventBase):
    event_type: Literal[EventType.STEP_COMPLETED] = EventType.STEP_COMPLETED
    record: StepRecord


class RunFinishedEvent(RunEventBase):
    event_type: Literal[EventType.RUN_FINISHED] = EventType.RUN_FINISHED
    status: RunStatus
    error: Optional[ErrorInfo] = None


RunEvent = Annotated[Union[RunStartedEvent, StepCompletedEvent, RunFinishedEvent], Field(discriminator="event_type")]
