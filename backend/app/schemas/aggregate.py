from typing import Literal

from pydantic import BaseModel


class AggregateGroup(BaseModel):
    name: str
    total: int
    favorable: int


class AggregateRequest(BaseModel):
    org_name: str
    model_name: str
    domain: str
    attribute_name: str
    groups: list[AggregateGroup]


class AggregateResponse(BaseModel):
    job_id: str
    mode: Literal["aggregate"]
