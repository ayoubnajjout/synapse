import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ShortText = Annotated[str, Field(min_length=1, max_length=200)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConversationCreate(StrictModel):
    title: ShortText = "New conversation"


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageCreate(StrictModel):
    id: uuid.UUID  # Client-generated id makes retries idempotent.
    content: str = Field(min_length=1, max_length=100_000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    conversation_id: uuid.UUID
    sequence: int
    role: str
    content: str
    provider: str | None
    model: str | None
    status: str
    created_at: datetime


class Generate(StrictModel):
    id: uuid.UUID
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=200)
    regenerate: bool = False


class MemoryCreate(StrictModel):
    content: str = Field(min_length=1, max_length=4000)
    enabled: bool = True


class MemoryPatch(StrictModel):
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    enabled: bool | None = None

    @field_validator("content", "enabled")
    @classmethod
    def not_null(cls, value):
        if value is None:
            raise ValueError("Value cannot be null")
        return value


class MemoryOut(MemoryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class Preferences(StrictModel):
    memory_enabled: bool = True
    context_chars: int = Field(default=24_000, ge=2000, le=200_000)
    max_messages: int = Field(default=40, ge=2, le=200)
    max_output_tokens: int = Field(default=2048, ge=128, le=32_768)


class ProviderConfig(StrictModel):
    api_base: str | None = Field(default=None, max_length=500)
    models: list[ShortText] = Field(default_factory=list, max_length=100)
    default_model: str | None = Field(default=None, max_length=200)

    @field_validator("api_base")
    @classmethod
    def http_url(cls, value):
        if not value:
            return None
        from urllib.parse import urlsplit
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Use an http(s) endpoint without credentials, query parameters or fragments")
        if parsed.port is not None and parsed.port == 0:
            raise ValueError("Use a port between 1 and 65535")
        return value.rstrip("/")


class SettingsPatch(StrictModel):
    preferences: Preferences | None = None
    providers: dict[str, ProviderConfig] | None = None


class ImportedMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=100_000)
    provider: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=200)
    # Exported identity is accepted but never reused.
    id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    sequence: int | None = None
    status: Literal["completed"] = "completed"
    created_at: datetime | None = None


class ImportedConversation(ConversationCreate):
    messages: list[ImportedMessage] = Field(default_factory=list, max_length=2000)
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ImportData(StrictModel):
    format: Literal["synapse"]
    version: Literal[1]
    conversations: list[ImportedConversation] = Field(min_length=1, max_length=200)
