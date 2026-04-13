from pydantic import BaseModel, Field


class SampleDataset(BaseModel):
    id: str
    name: str
    description: str
    rows: int
    known_biases: list[str] = Field(default_factory=list)
    path: str


class SamplesResponse(BaseModel):
    datasets: list[SampleDataset]
