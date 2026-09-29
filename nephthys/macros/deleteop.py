from nephthys.macros.types import Macro
from nephthys.utils import prometheus
from nephthys.utils.env import env


class DeleteOP(Macro):
    name = "deleteop"
    can_run_on_closed = True

    async def run(self, ticket, helper, **kwargs):
        await prometheus.delete_message(
            ts=ticket.msg_ts,
            channel=env.slack_help_channel,
            reason=f"?deleteop by <@{helper.slack_id}>",
        )
