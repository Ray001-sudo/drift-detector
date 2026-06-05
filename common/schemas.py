from pydantic import BaseModel, ConfigDict, Field, UUID4, StrictFloat, StrictInt
from typing import Dict, Any, Optional, Union, List
from datetime import datetime

class InferenceRequest(BaseModel):
    request_id: str
    features: Dict[str, Union[float, int, str]]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class FeatureVector(BaseModel):
    request_id: str
    model_version: str
    features: Dict[str, float]  # We assume encoded to float for detectors
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class DriftScoreEventSchema(BaseModel):
    window_id: str
    feature_name: str
    detector_type: str
    score: float
    is_drifted: bool
    model_version: str
    window_start: datetime
    window_end: datetime
    sample_count: int
    metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

class AlertRuleSchema(BaseModel):
    id: UUID4
    feature_name: Optional[str] = None
    detector_type: str
    threshold: float
    severity: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class AlertSchema(BaseModel):
    id: UUID4
    rule_id: UUID4
    feature_name: str
    detector_type: str
    score: float
    threshold: float
    severity: str
    model_version: str
    window_id: str
    fired_at: datetime
    resolved_at: Optional[datetime] = None
    suppressed: bool

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None

class UserSchema(BaseModel):
    id: UUID4
    username: str
    role: str
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)

class BaselineRegisteredEvent(BaseModel):
    model_version: str
    feature_name: str  
    sample_count: int
    registered_at: datetime
    registered_by: str
