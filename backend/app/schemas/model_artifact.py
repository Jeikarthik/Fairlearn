from pydantic import BaseModel


class ModelUploadResponse(BaseModel):
    job_id: str
    filename: str
    status: str
