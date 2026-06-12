from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Backend configuration.

    `data_dir` is the single source of truth for where all on-disk state lives
    (SQLite DB, OAuth tokens, log files, temp uploads, settings.json). Every
    other path is derived from it via @property so that overriding `data_dir`
    via the POSTBELL_DATA_DIR env var redirects ALL state in one shot. This is
    what lets the packaged Electron app point the bundled backend at
    `%APPDATA%/Postbell` without having to set five separate env vars.

    Default (`data`) preserves the existing dev behaviour: paths resolve
    relative to whatever cwd the backend is launched from.
    """

    data_dir: Path = Path("data")
    gemini_api_key: str = ""
    youtube_daily_quota: int = 10000
    upload_chunk_size_mb: int = 10

    # Derived paths — properties so that they stay in sync even if the user
    # mutates `settings.data_dir` directly (tests do this) and so that the
    # POSTBELL_DATA_DIR env var only needs to set one value.

    @property
    def database_url(self) -> str:
        # Use forward slashes (as_posix) so SQLAlchemy's sqlite:/// URL parser
        # accepts Windows paths without backslash-escaping headaches.
        return f"sqlite:///{(self.data_dir / 'postbell.db').as_posix()}"

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / "temp"

    @property
    def tokens_dir(self) -> Path:
        return self.data_dir / "tokens"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"

    model_config = {"env_file": ".env", "env_prefix": "POSTBELL_"}


settings = Settings()
