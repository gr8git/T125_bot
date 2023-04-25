from pydantic import BaseSettings, SecretStr


class Settings(BaseSettings):
    driver: SecretStr
    server: SecretStr
    database: SecretStr
    username: SecretStr
    password: SecretStr
    api_token: SecretStr
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'

config = Settings()


