from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class FieldSpec(Strict):
    name: str = Field(pattern=r'^[a-zA-Z_][a-zA-Z0-9_]{0,59}$')
    type: Literal['string', 'integer', 'number', 'boolean', 'timestamp']
    required: bool = True
    nullable: bool = False
    aliases: list[str] = Field(default_factory=list, max_length=10)
    enum: list[str] = Field(default_factory=list, max_length=30)
    semantic: str | None = Field(default=None, max_length=60)
    unit: Literal['cents', 'usd'] | None = None

    @model_validator(mode='after')
    def coherent(self):
        if self.enum and self.type != 'string':
            raise ValueError('Enums are supported only for string fields')
        if self.unit and (not self.semantic or self.type not in {'integer', 'number'}):
            raise ValueError('Money units require a numeric field with a semantic identity')
        if self.name in self.aliases or len(self.aliases) != len(set(self.aliases)):
            raise ValueError('Aliases must be unique and different from the field name')
        return self


class Contract(Strict):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=40)
    fields: list[FieldSpec] = Field(min_length=1, max_length=40)
    allow_extra: bool = True
    identity_field: str | None = None

    @model_validator(mode='after')
    def unique(self):
        names = [f.name for f in self.fields]
        semantics = [f.semantic for f in self.fields if f.semantic]
        if len(set(names)) != len(names) or len(set(semantics)) != len(semantics):
            raise ValueError('Field names and semantic identities must be unique')
        if self.identity_field and self.identity_field not in names:
            raise ValueError('Identity field must exist')
        return self


class Rename(Strict):
    op: Literal['rename']
    source: str
    target: str


class Cast(Strict):
    op: Literal['cast']
    field: str
    to: Literal['string', 'integer', 'number', 'boolean', 'timestamp']


class Scale(Strict):
    op: Literal['scale']
    field: str
    factor: Literal['0.01', '100']


Operation = Annotated[Rename | Cast | Scale, Field(discriminator='op')]


class Plan(Strict):
    rationale: str = Field(min_length=1, max_length=1500)
    operations: list[Operation] = Field(default_factory=list, max_length=80)


class ReplayRequest(Strict):
    title: str = Field(min_length=1, max_length=150)
    source: Contract
    target: Contract
    events: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
    plan: Plan | None = None
    analyst: Literal['rules', 'ollama'] = 'rules'
    max_reject_rate: float = Field(default=0, ge=0, le=1)
