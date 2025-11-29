from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    grocy_api_url: str = "http://homeassistant.local:9192/api"
    grocy_api_key: str
    ha_token: str

    # Automatically reads from .env file
    model_config = SettingsConfigDict(env_file=".env")

# Global instance
settings = Settings()
