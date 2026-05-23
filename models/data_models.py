from pydantic import BaseModel, Field
from typing import List, Optional

# ======================================================
# INCOMING SCHEMAS
# ======================================================

class TaskGenerateRequest(BaseModel):
    taskTitle: str = Field(..., description="Title of the main task")
    concepts: str = Field(..., description="Comma-separated concepts or learning topics")
    duration: str = Field("2 weeks", description="Overall study duration (e.g. 4 weeks, 10 hours)")
    scheduleType: str = Field("daily", description="daily or weekly milestones schedule")
    resourcePreference: str = Field("mixed", description="playlist, video, or mixed")
    skillLevel: Optional[str] = Field("intermediate", description="beginner, intermediate, or advanced")
    enginePreference: Optional[str] = Field("hybrid", description="hybrid, gemini, or crawl")
    geminiApiKey: Optional[str] = Field(None, description="Optional custom user Gemini API Key")



class SearchResourcesRequest(BaseModel):
    query: str = Field(..., description="Topic search term")
    searchType: str = Field("mixed", description="playlist, video, or mixed")
    limit: int = Field(5, description="Number of results to return")


class AnalyzeConceptsRequest(BaseModel):
    text: str = Field(..., description="Text input to extract topics from")

# ======================================================
# OUTGOING SCHEMAS
# ======================================================

class LearningResource(BaseModel):
    title: str
    url: str
    type: str  # playlist, video, doc, pdf, site, roadmap
    category: str
    estimatedDuration: str
    thumbnail: str
    sourcePlatform: str
    difficulty: str  # beginner, intermediate, advanced
    aiScore: int
    tags: List[str]


class SuggestedPlanItem(BaseModel):
    period: str  # Week 1, Day 3, etc.
    topics: List[str]
    tasks: List[str]


class TaskGenerateResponse(BaseModel):
    success: bool
    task: dict  # contains title, duration, scheduleType
    categories: List[str]
    resources: List[LearningResource]
    suggestedPlan: List[SuggestedPlanItem]
