from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, field_validator

class PlanCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    is_public: bool = False

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be blank")
        return v

    @field_validator("end_date")
    @classmethod
    def dates_order(cls, v, info):
        start = info.data.get("start_date")
        if v and start and v < start:
            raise ValueError("end_date must be >= start_date")
        return v

class PlanUpdate(BaseModel):
    version: int = Field(gt=0)
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    is_public: Optional[bool] = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("title must not be blank")
        return v

class LocationOut(BaseModel):
    id: str
    travel_plan_id: str
    name: str
    address: Optional[str]
    latitude: Optional[Decimal]
    longitude: Optional[Decimal]
    visit_order: int
    arrival_date: Optional[datetime]
    departure_date: Optional[datetime]
    budget: Optional[Decimal]
    notes: Optional[str]
    created_at: datetime

class PlanOut(BaseModel):
    id: str
    title: str
    description: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    budget: Optional[Decimal]
    currency: str
    is_public: bool
    version: int
    created_at: datetime
    updated_at: datetime
    locations: list[LocationOut] = []

class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: Optional[str] = None
    latitude: Optional[Decimal] = Field(default=None, ge=-90, le=90)
    longitude: Optional[Decimal] = Field(default=None, ge=-180, le=180)
    visit_order: Optional[int] = Field(default=None, gt=0)
    arrival_date: Optional[datetime] = None
    departure_date: Optional[datetime] = None
    budget: Optional[Decimal] = Field(default=None, ge=0)
    notes: Optional[str] = None

class LocationUpdate(BaseModel):
    version: int = Field(gt=0)
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    address: Optional[str] = None
    latitude: Optional[Decimal] = Field(default=None, ge=-90, le=90)
    longitude: Optional[Decimal] = Field(default=None, ge=-180, le=180)
    visit_order: Optional[int] = Field(default=None, gt=0)
    arrival_date: Optional[datetime] = None
    departure_date: Optional[datetime] = None
    budget: Optional[Decimal] = Field(default=None, ge=0)
    notes: Optional[str] = None