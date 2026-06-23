"""
集中配置模块。
所有模块从本模块导入配置对象，不直接读 os.environ。

使用 pydantic-settings 加载 .env 文件，校验必填字段。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """统一配置对象，从 .env 文件和环境变量加载。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- DeepSeek API ----
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_pro_model: str = "deepseek-v4-pro"
    deepseek_flash_model: str = "deepseek-v4-flash"

    # ---- PostgreSQL ----
    database_url: str

    # ---- 和风天气 ----
    heweather_api_key: str = ""
    heweather_base_url: str = "https://devapi.qweather.com/v7"

    # ---- cc-connect ----
    cc_connect_api_url: str = "http://localhost:9527"
    cc_connect_webhook_secret: str = ""
    wechat_user_id: str = ""

    # ---- 用户参数 ----
    user_height_cm: float = 175.0

    # ---- 应用配置 ----
    app_port: int = 8000
    app_env: str = "production"
    charts_dir: str = "/app/charts"
    charts_retention_hours: int = 24

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


# 全局单例，所有模块从此导入
config = Config()
