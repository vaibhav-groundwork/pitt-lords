from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All config lives here and is read from environment variables / .env.
    Nothing here should ever be hardcoded elsewhere in the codebase --
    if you find yourself typing a connection string or API key inline,
    it belongs in here instead.
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://pittlords:localdevpassword@localhost:5432/pittlords"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    environment: str = "development"  # development | production
    max_upload_mb: int = 10
    rate_limit_per_minute: int = 20


settings = Settings()
