from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False)

    provider: str = "openliga"

    # Rate limiting
    rate_limit_rps: float = 5.0

    # Exponential backoff
    max_retries: int = 3
    backoff_base_delay: float = 0.5
    backoff_max_delay: float = 10.0

    # Body truncation for logging (chars)
    log_body_max_chars: int = 200


settings = Settings()
