from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class StorageDiskInfo(BaseModel):
    total_bytes: int
    total_human: str
    used_bytes: int
    used_human: str
    free_bytes: int
    free_human: str
    used_percent: float
    free_percent: float


class StorageCategoryInfo(BaseModel):
    category: str
    label: str
    size_bytes: int
    size_human: str
    item_count: Optional[int] = None
    path: str
    is_protected: bool = False
    cleanable: bool = False
    cleanable_bytes: Optional[int] = None
    cleanable_human: Optional[str] = None
    description: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class StorageUsageResponse(BaseModel):
    disk: StorageDiskInfo
    categories: Dict[str, StorageCategoryInfo]
    total_data_bytes: int
    total_data_human: str
    total_cleanable_bytes: int
    total_cleanable_human: str


class StorageCleanRequest(BaseModel):
    targets: List[str] = Field(
        default_factory=lambda: ["temp_caches"],
        description="List of cleanup targets: 'temp_caches', 'logs', 'old_toolkit_tasks', 'vacuum_db'",
    )
    older_than_days: int = Field(
        default=7,
        ge=0,
        le=365,
        description="Retention threshold in days for old toolkit tasks",
    )


class StorageCleanResponse(BaseModel):
    success: bool
    freed_bytes: int
    freed_human: str
    targets_processed: List[str]
    details: Dict[str, Any]
    storage: StorageUsageResponse
