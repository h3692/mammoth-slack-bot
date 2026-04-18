from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SubmissionType(str, Enum):
    URL = "URL"
    IDEA = "IDEA"
    KUDOS = "KUDOS"
    ANONYMOUS_REPORT = "ANONYMOUS_REPORT"


class SubmissionStatus(str, Enum):
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    DISMISSED = "DISMISSED"
    SAVED_TO_CAMPAIGN = "SAVED_TO_CAMPAIGN"


class Submission(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: SubmissionType
    text: str
    summary: Optional[List[str]] = None
    url: Optional[str] = None
    submitter_slack_id: str
    submitter_name: str
    channel_id: str
    message_ts: str
    reaction_count: int = 0
    reactions: Dict[str, str] = Field(default_factory=dict)  # user_id -> emoji
    is_high_value: bool = False
    is_anonymous: bool = False
    points_awarded: int = 0
    status: SubmissionStatus = SubmissionStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Campaign(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    submission_id: str
    title: str
    description: str
    source_url: Optional[str] = None
    source_type: SubmissionType = SubmissionType.IDEA
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatsResponse(BaseModel):
    total_submissions: int = 0
    validated_count: int = 0
    anonymous_count: int = 0
    total_points_awarded: int = 0
    campaigns_created: int = 0
    submissions_by_type: Dict[str, int] = Field(default_factory=dict)
    top_contributors: List[Dict] = Field(default_factory=list)


class StatusUpdate(BaseModel):
    status: SubmissionStatus


class CampaignCreate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class DigestRequest(BaseModel):
    manager_user_id: Optional[str] = None
