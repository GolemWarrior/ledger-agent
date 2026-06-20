from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    database_url_sync: str
    database_url_eval: str
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"
    anthropic_api_key: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
