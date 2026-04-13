from pydantic import BaseModel


class CompareHistoryResponse(BaseModel):
    comparisons: list[dict[str, str | float]]
