from pydantic import BaseModel, Field
from typing import Dict, Any


class HealthResponse(BaseModel):
    status: str = Field("ok", description="Overall system health status")
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Current environment (development, production, etc.)")
    system_info: Dict[str, Any] = Field(
        default_factory=dict,
        description="Basic system information (ffmpeg availability, storage, etc.)",
    )
