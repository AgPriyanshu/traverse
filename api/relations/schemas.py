from enum import StrEnum

from pydantic import BaseModel, Field

from ..contracts.enums import AssertionType
from ..graph import ontology

# Guided decoding constrains the model to this vocabulary. Sprint 3's spike saw
# Qwen3-8B paraphrase to ``acquainted_with`` when the predicate was a free
# string, so the ontology is enforced at decode time as well as at validation.
ExtractablePredicate = StrEnum(
    "ExtractablePredicate",
    {
        name.upper(): name
        for name, spec in ontology.PREDICATES.items()
        if spec.extracted
    },
)


class RawRelation(BaseModel):
    subject: str
    predicate: ExtractablePredicate
    object: str
    assertion_type: AssertionType = AssertionType.NARRATED
    asserted_by: str | None = None
    quote: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RelationSweepOutput(BaseModel):
    relations: list[RawRelation] = Field(default_factory=list)
