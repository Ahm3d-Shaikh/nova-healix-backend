from enum import StrEnum

from pydantic import BaseModel


class Provenance(StrEnum):
    NASA = "nasa"  # published NASA limit / brief
    CSA = "csa"  # published CSA figure
    PUBLISHED_METHOD = "published_method"  # validated scale / test (Hughes, Basner)
    ILLUSTRATIVE = "illustrative"  # our own design choice - must be labelled as such


class ThresholdInfo(BaseModel):
    hazard: str
    name: str
    value: float | str
    unit: str
    provenance: Provenance
    source: str


class DataProvenanceRow(BaseModel):
    data: str
    status: str  # "real" | "real (published)" | "real (validated)" | "simulated"
    source: str


class SourceLink(BaseModel):
    title: str
    url: str


class MetaResponse(BaseModel):
    project: str
    version: str
    disclaimer: str
    data: list[DataProvenanceRow]
    thresholds: list[ThresholdInfo]
    sources: list[SourceLink]
