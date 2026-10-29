"""Request models. Responses are plain dicts built in services/routes (documented in README)."""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=False)

    login_id: str = Field(min_length=3, max_length=254, alias="loginId")
    password: str = Field(min_length=1, max_length=256, repr=False)

    @field_validator("login_id")
    @classmethod
    def _clean_login(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3 or _CONTROL.search(v):
            raise ValueError("loginId must be 3-254 printable characters")
        return v

    @field_validator("password")
    @classmethod
    def _clean_password(cls, v: str) -> str:
        if _CONTROL.search(v):
            raise ValueError("password contains control characters")
        return v


# ---- attendance planning ------------------------------------------------------
from typing import Literal  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402


class AdjustmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_key: str = Field(min_length=1, max_length=200)
    session_key: str = Field(min_length=1, max_length=300)
    status: Literal["present", "absent"]


class ScenarioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_key: str = Field(min_length=1, max_length=200)
    target: float | None = Field(default=None, gt=0, lt=100)
    attend: int = Field(default=0, ge=0, le=1000)
    miss: int = Field(default=0, ge=0, le=1000)
    sequence: list[Literal["present", "absent"]] | None = Field(default=None, max_length=1000)
