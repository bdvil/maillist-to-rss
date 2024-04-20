import shutil

import yaml
from pydantic import BaseModel

from maillist_to_rss.constants import PROJECT_DIR


class Config(BaseModel):
    email_addr: str
    email_server: str
    email_pass: str
    imap_port: int

    database_url: str

    server_url: str
    server_port: int


def load_config() -> Config:
    default_config_path = PROJECT_DIR / "example-config.yaml"
    config_path = PROJECT_DIR / "config.yaml"
    if not config_path.exists():
        shutil.copyfile(default_config_path, config_path)
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return Config.model_validate(data)
