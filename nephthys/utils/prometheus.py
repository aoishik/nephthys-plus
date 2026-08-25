import logging

from nephthys.utils.env import env


async def delete_message(ts: str, reason: str) -> bool:
    """Delete a Slack message via the Prometheus moderation API.

    Returns True if the message was deleted, False otherwise.
    """
    async with env.session.post(
        f"{env.prometheus_base_url}/api/v1/messages/delete",
        headers={"Authorization": f"Bearer {env.prometheus_api_key}"},
        json={"ts": ts, "reason": reason},
    ) as resp:
        body = await resp.json()
        if resp.status != 200 or ts not in body.get("deleted", []):
            logging.error(f"Prometheus failed to delete message ts={ts}: {body}")
            return False
        return True
