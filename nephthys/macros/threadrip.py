from nephthys.macros.types import Macro
from nephthys.utils import prometheus
from nephthys.utils.env import env


class ThreadRip(Macro):
    name = "threadrip"
    can_run_on_closed = True

    async def run(self, ticket, helper, **kwargs):
        """
        Like ?thread, but nukes the whole thread: deletes the original ticket
        message and every reply via the Prometheus moderation API.
        """
        replies = await env.slack_client.conversations_replies(
            channel=env.slack_help_channel, ts=ticket.msg_ts
        )
        # Delete replies first, root message last (deleting root can orphan the fetch)
        for msg in reversed(replies.get("messages", [])):
            if "ts" in msg:
                await prometheus.delete_message(
                    ts=msg["ts"], reason=f"?threadrip by {helper.slack_id}"
                )
