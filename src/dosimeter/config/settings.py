"""
Settings for the whole project, checked when the app starts.

Environment variables start with DOSIMETER_. To reach a value inside a group,
join the names with two underscores:
DOSIMETER_BOUNDS__MAX_TOOL_INVOCATIONS_PER_TURN=6.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from dosimeter.errors import ConfigurationError


TEXT_ROLES = ("reasoning", "fast", "judge")
EMBEDDING_ROLE = "embedding"
MULTIMODAL_ROLE = "multimodal"
MODEL_ROLES = (*TEXT_ROLES, EMBEDDING_ROLE, MULTIMODAL_ROLE)


class DatabaseSettings(BaseSettings):
    """
    The database on its own, loaded separately from the rest, so a migration or
    a seed run does not need the model ids and buckets it will never touch.
    """

    model_config = SettingsConfigDict(
        env_prefix="DOSIMETER_DB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    host: str = Field(min_length=1)
    port: int = Field(default=5432, gt=0, lt=65536)
    name: str = Field(min_length=1)
    user: str = Field(min_length=1)
    use_iam_auth: bool = True
    password: SecretStr | None = None
    sslmode: str = Field(default="require", min_length=1)
    connect_timeout_seconds: int = Field(default=10, gt=0)

    @model_validator(mode="after")
    def _password_required_without_iam_auth(self) -> DatabaseSettings:
        if not self.use_iam_auth and self.password is None:
            raise ValueError("password is required when use_iam_auth is false")
        return self


class NearBoundaryMargins(BaseModel):
    """
    How close to a limit still counts as close. Each one is written in the same
    unit as the limit it belongs to, never as a percentage.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # R1
    annual_limit_tede_rem: float = Field(default=0.25, ge=0)
    annual_limit_lens_rem: float = Field(default=0.75, ge=0)
    annual_limit_shallow_rem: float = Field(default=2.5, ge=0)

    # R2
    immediate_notification_tede_rem: float = Field(default=1.0, ge=0)
    immediate_notification_lens_rem: float = Field(default=3.0, ge=0)
    immediate_notification_shallow_rad: float = Field(default=10.0, ge=0)

    # R3
    twenty_four_hour_tede_rem: float = Field(default=0.25, ge=0)
    twenty_four_hour_lens_rem: float = Field(default=0.75, ge=0)
    twenty_four_hour_shallow_rem: float = Field(default=2.5, ge=0)

    # R4
    intake_ali_multiple: float = Field(default=0.05, ge=0)

    # R5
    report_window_days: int = Field(default=2, ge=0)


class Bounds(BaseModel):
    """Limits on what one request is allowed to do."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_tokens_per_call: dict[str, int] = Field(
        default_factory=lambda: {
            "coordinator": 4096,
            "notification": 4096,
            "written_report": 4096,
            "equipment": 2048,
            "reviewer": 4096,
            "judge": 2048,
        }
    )
    default_max_tokens_per_call: int = Field(default=2048, gt=0)
    max_tool_invocations_per_turn: int = Field(default=8, gt=0)
    max_recursion_depth: int = Field(default=12, gt=0)
    max_retrieved_chunks: int = Field(default=12, gt=0)
    max_retrieved_tokens: int = Field(default=8000, gt=0)
    per_turn_wall_clock_seconds: float = Field(default=180.0, gt=0)
    per_call_http_timeout_seconds: float = Field(default=30.0, gt=0)
    max_session_tokens: int = Field(default=120_000, gt=0)
    reviewer_iteration_cap: int = Field(default=3, gt=0)
    max_artifacts_per_packet: int = Field(default=12, gt=0)
    max_artifact_bytes: int = Field(default=25 * 1024 * 1024, gt=0)

    def tokens_for(self, agent: str) -> int:
        """Token limit for one agent, or the default if it has none of its own."""

        return self.max_tokens_per_call.get(agent, self.default_max_tokens_per_call)


class Settings(BaseSettings):
    """Everything the project can be configured with."""

    model_config = SettingsConfigDict(
        env_prefix="DOSIMETER_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        populate_by_name=True,
        protected_namespaces=(),
    )

    aws_region: str = Field(default="us-east-1", pattern=r"^us-east-\d$")

    bedrock_model_id: str = Field(min_length=1, validation_alias="BEDROCK_MODEL_ID")
    bedrock_embed_model_id: str = Field(min_length=1, validation_alias="BEDROCK_EMBED_MODEL_ID")
    bedrock_multimodal_model_id: str | None = Field(
        default=None,
        validation_alias="BEDROCK_MULTIMODAL_MODEL_ID",
    )

    knowledge_base_id: str = Field(min_length=1)
    knowledge_base_data_source_id: str | None = None
    guardrail_id: str = Field(min_length=1)
    guardrail_version: str = Field(default="DRAFT", min_length=1)

    corpus_bucket: str = Field(min_length=1, validation_alias="AWS_CORPUS_BUCKET_NAME")
    packet_bucket: str = Field(min_length=1, validation_alias="AWS_PACKET_BUCKET_NAME")
    textract_output_prefix: str = Field(default="textract/")

    confidence_floor: float = Field(default=0.60, ge=0, le=1)
    similarity_threshold: float = Field(default=0.50, ge=0, le=1)

    near_boundary_margins: NearBoundaryMargins = Field(default_factory=NearBoundaryMargins)
    bounds: Bounds = Field(default_factory=Bounds)

    tool_api_base_url: str = Field(default="http://127.0.0.1:8080", min_length=1)
    tool_api_dev_identity: bool = False
    tool_api_identity_header: str = Field(default="X-Dosimeter-Officer", min_length=1)

    log_level: str = Field(default="INFO", min_length=1)

    def model_for(self, role: str) -> str:
        """
        The model id for one role. Reasoning, fast and judge share one model
        with different prompts and tools; the run record still says which role
        the call was made in.
        """

        if role in TEXT_ROLES:
            return self.bedrock_model_id
        if role == EMBEDDING_ROLE:
            return self.bedrock_embed_model_id
        if role == MULTIMODAL_ROLE:
            return self.bedrock_multimodal_model_id or self.bedrock_model_id

        raise ConfigurationError(f"unknown model role: {role}", field="role")


def _describe(error: ValidationError) -> str:
    lines = []
    for item in error.errors():
        field = ".".join(str(part) for part in item["loc"]) or "<model>"
        lines.append(f"{field}: {item['msg']}")
    return "; ".join(lines)


def load_settings(**overrides: Any) -> Settings:
    """Read the settings, or fail and say which one is wrong."""

    try:
        return Settings(**overrides)
    except ValidationError as error:
        fields = sorted(
            {".".join(str(part) for part in item["loc"]) or "<model>" for item in error.errors()}
        )
        raise ConfigurationError(
            f"Invalid configuration: {_describe(error)}",
            fields=fields,
        ) from error


def load_database_settings(**overrides: Any) -> DatabaseSettings:
    """Read the database settings on their own, or fail naming the field."""

    try:
        return DatabaseSettings(**overrides)
    except ValidationError as error:
        raise ConfigurationError(
            f"Invalid database configuration: {_describe(error)}",
            fields=sorted({".".join(str(part) for part in item["loc"]) for item in error.errors()}),
        ) from error


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    """Read the database settings once and reuse them."""

    return load_database_settings()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Read the settings once and reuse them."""

    return load_settings()


__all__ = [
    "Bounds",
    "DatabaseSettings",
    "MODEL_ROLES",
    "NearBoundaryMargins",
    "Settings",
    "get_database_settings",
    "get_settings",
    "load_database_settings",
    "load_settings",
]
