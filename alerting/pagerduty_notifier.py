import httpx
import logging
from common.config import settings

logger = logging.getLogger(__name__)

async def send_pagerduty_alert(summary: str, source: str, severity: str = "critical") -> None:
    routing_key = settings.PAGERDUTY_ROUTING_KEY.get_secret_value() if settings.PAGERDUTY_ROUTING_KEY else ""
    if not routing_key or routing_key == "your-pd-routing-key":
        logger.warning("PagerDuty routing key not configured or is default. Skipping PagerDuty alert.")
        return

    url = "https://events.pagerduty.com/v2/enqueue"
    payload = {
        "routing_key": routing_key,
        "event_action": "trigger",
        "payload": {
            "summary": summary,
            "source": source,
            "severity": severity,
        }
    }

    try:
        async with httpx.AsyncClient(verify=True) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to send PagerDuty alert: {e}")
