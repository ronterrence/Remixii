"""AI Remix Studio."""

import os

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
_local_hosts = ("localhost", "127.0.0.1", "::1")
_no_proxy = [entry.strip() for entry in os.environ.get("NO_PROXY", "").split(",") if entry.strip()]
for _host in _local_hosts:
    if _host not in _no_proxy:
        _no_proxy.append(_host)
os.environ["NO_PROXY"] = ",".join(_no_proxy)

__version__ = "0.1.0"
