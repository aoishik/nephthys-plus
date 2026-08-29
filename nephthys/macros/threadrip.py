from nephthys.macros.types import Macro
from nephthys.utils import prometheus
from nephthys.utils.env import env


class ThreadRip(Macro):
    name = "threadrip"
    can_run_on_closed = True

    async def run(self, ticket, helper, **kwargs):
        """
        Like ?thread, but nukes the whole thread: deletes the original ticket
        message and every reply.
        """
        await prometheus.delete_thread(
            thread_ts=ticket.msg_ts,
            channel=env.slack_help_channel,
            reason=f"?threadrip by {helper.slack_id}",
        )
