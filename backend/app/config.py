"""환경 설정."""

from __future__ import annotations

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # File storage
    upload_dir: str = "./uploads"
    output_dir: str = "./outputs"
    max_file_size_mb: int = 50

    # Agent
    agent_skills_dir: str = os.path.join(os.path.dirname(__file__), "..", "..", "agent_skills")
    agent_max_steps: int = 200

    # GenAI Gateway
    genai_api_url: str = "https://genai-sharedservice-americas.pwcinternal.com"
    genai_api_key: str = ""
    genai_model: str = "bedrock.anthropic.claude-sonnet-4-6"

    # Database
    database_url: str = "postgresql://ksyjerry:3edc1qaz@localhost:5432/sara"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Cleanup
    job_retention_hours: int = 24

    model_config = {
        "env_file": os.path.join(os.path.dirname(__file__), "..", ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
