from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Intent = Literal['report_question','image_search','image_and_report_question','metadata_lookup','out_of_scope_or_insufficient']
Tool = Literal['report_search','image_search','metadata_lookup']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)

class Filters(StrictModel):
    patient_id: str | None = Field(default=None, max_length=128)
    image_id: str | None = Field(default=None, max_length=128)
    modality: Literal['Mammogram','Ultrasound'] | None = None
    split: Literal['train'] = 'train'
    has_report: bool | None = None
    has_structured_report: bool | None = None
    birads: str | None = Field(default=None, pattern=r'^[0-6][a-cA-C]?$')

class Report(StrictModel):
    passage_id: str
    text: str = Field(max_length=20000)
    patient_id: str
    source: str
    split: Literal['train']
    modality: str | None = None
    distance: float | None = None
    similarity: float | None = None
    rank: int = Field(ge=1)

class ImageHit(StrictModel):
    image_id: str
    patient_id: str
    modality: Literal['Mammogram','Ultrasound']
    split: Literal['train']
    similarity: float
    rank: int = Field(ge=1)
    source_image_reference: str
    report_sources: list[str] = Field(default_factory=list)
    association_level: str = 'patient'
    association_warning: str | None = None
    embedding_model: Literal['google/vit-base-patch16-224-in21k']

class RegistryEntry(StrictModel):
    kind: Literal['report','image']
    id: str
    patient_id: str
    source: str
    split: Literal['train']
    modality: str | None = None
    rank: int
    similarity: float | None = None

class Checker(StrictModel):
    decision: str = 'not_checked'
    problems: list[str] = Field(default_factory=list)
    checked_passage_ids: list[str] = Field(default_factory=list)

class MetadataRow(StrictModel):
    patient_id: str
    split: Literal['train']
    modalities: list[str]
    image_ids: list[str]
    report_sources: list[str]
    has_report: bool
    has_structured_report: bool
    image_count: int
    report_count: int
    association_exam_verified: bool = False
    association_warning: str | None = None

class State(StrictModel):
    request_id: str = Field(min_length=1, max_length=128)
    question: str = Field(default='', max_length=2000)
    query: str = Field(default='', max_length=2200)
    patient_id: str | None = Field(default=None, max_length=128)
    filters: Filters = Field(default_factory=Filters)
    intent: Intent = 'out_of_scope_or_insufficient'
    tools: list[Tool] = Field(default_factory=list)
    needs_generation: bool = False
    retry_count: int = Field(default=0, ge=0, le=1)
    status: str = 'pending'
    reports: list[Report] = Field(default_factory=list, max_length=20)
    images: list[ImageHit] = Field(default_factory=list, max_length=20)
    metadata: list[MetadataRow] = Field(default_factory=list)
    registry: list[RegistryEntry] = Field(default_factory=list)
    generation_evidence: list[Report] = Field(default_factory=list, max_length=5)
    candidate_answer: str = Field(default='', max_length=20000)
    answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    checker: Checker = Field(default_factory=Checker)
    tools_called: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

class ToolRequest(StrictModel):
    state: State

class ReportRequest(ToolRequest):
    top_k: int = Field(default=5, ge=1, le=10)

class ImageRequest(ReportRequest):
    image_base64: str = Field(min_length=1, max_length=28000000)

class CheckRequest(ToolRequest):
    stage: Literal['evidence','answer'] = 'evidence'

class ToolResponse(StrictModel):
    state: State

class JobResponse(ToolResponse):
    job_id: str
    kind: Literal['report','image']

class CollectRequest(ToolRequest):
    jobs: list[str] = Field(min_length=2, max_length=2)
