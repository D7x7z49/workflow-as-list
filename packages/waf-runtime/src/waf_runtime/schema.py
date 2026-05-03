# packages/waf-runtime/src/waf_runtime/schema.py


from pydantic import BaseModel, Field, NonNegativeInt

from waf_core.schema import Identifier, StepLine, WorkflowModule


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
    resolved_text: str
    result_text: str
    success: bool
