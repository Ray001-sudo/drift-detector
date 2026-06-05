import logging
import structlog
from typing import Any, Dict

def redact_secrets(logger: logging.Logger, name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitise logs to prevent secrets leaking."""
    secrets = ["password", "token", "secret", "jwt", "authorization"]
    for k, v in event_dict.items():
        if any(sec in k.lower() for sec in secrets):
            event_dict[k] = "***REDACTED***"
    return event_dict

def setup_logging() -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            redact_secrets,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
    )
