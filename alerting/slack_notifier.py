import httpx
import logging
from common.config import settings

logger = logging.getLogger(__name__)

async def send_slack_alert(message: str) -> None:
    webhook_url = settings.SLACK_WEBHOOK_URL
    if not webhook_url or webhook_url == "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX":
        logger.warning("Slack webhook not configured or is default. Skipping Slack notification.")
        return

    payload = {"text": message}
    try:
        async with httpx.AsyncClient(verify=True) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to send Slack alert: {e}")
