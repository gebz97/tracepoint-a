import os

# pyrefly: ignore [untyped-import]
import yaml

_CONFIG_PATH = os.environ.get(
    "TPA_CONFIG",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml"),
)

_cfg = None


def load_config() -> dict:
    global _cfg
    if _cfg is None:
        with open(_CONFIG_PATH) as f:
            _cfg = yaml.safe_load(f)
    return _cfg


def get_credential(name: str) -> dict:
    cfg = load_config()
    creds = cfg.get("credentials", {})
    if name not in creds:
        raise KeyError(f"credential '{name}' not found in config")
    return creds[name]


def get_ssh_settings() -> dict:
    cfg = load_config()
    return cfg.get("ssh", {"port": 22, "timeout": 30, "max_workers": 32})


def get_database_url() -> str:
    cfg = load_config()
    return cfg["database"]["url"]


def get_satellite_settings() -> dict:
    cfg = load_config()
    sat = cfg.get("satellite")
    if not sat:
        raise KeyError("'satellite' section missing from config")
    url = sat.get("url")
    if not url:
        raise KeyError("'satellite.url' missing from config")
    return {
        "url": url,
        "username": sat.get("username"),
        "password": sat.get("password"),
        "api_token": sat.get("token"),
        "verify_ssl": sat.get("verify_ssl", True),
        "timeout": sat.get("timeout", 30),
        "per_page": sat.get("per_page", 100),
        "max_workers": sat.get("max_workers", 16),
    }
