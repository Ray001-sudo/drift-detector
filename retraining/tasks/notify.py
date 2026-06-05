import os
import httpx

def notify_promotion(promotion_result: dict) -> None:
    if promotion_result.get("status") != "promoted":
        return
        
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url or "XXXX" in webhook_url:
        return
        
    msg = (
        f"✅ *Model Retrained & Promoted*\n"
        f"New Version: v{promotion_result['new_version']}\n"
        f"Old F1: {promotion_result['old_f1']:.4f}\n"
        f"New F1: {promotion_result['new_f1']:.4f}\n"
        f"Run ID: {promotion_result['run_id']}"
    )
    
    httpx.post(webhook_url, json={"text": msg})
