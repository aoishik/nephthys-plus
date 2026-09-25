from nephthys.actions.resolve import resolve
from nephthys.database.tables import User
from nephthys.macros.types import Macro
from nephthys.utils.env import env
from nephthys.utils.slack_user import get_user_profile
from nephthys.utils.ticket_methods import reply_to_ticket


class Hackatime(Macro):
    name = "hackatime"
    post_as_helper = True

    async def run(self, ticket, helper, **kwargs):
        """
        A simple macro telling people to use #hackatime-help.
        """
        sender = await User.objects().where(User.id == ticket.opened_by).first()
        if not sender:
            return
        user = await get_user_profile(sender.slack_id)
        username, icon_url = await self.helper_identity(helper)
        await reply_to_ticket(
            text=env.transcript.hackatime_macro.replace("(user)", user.display_name()),
            ticket=ticket,
            client=env.slack_client,
            username=username,
            icon_url=icon_url,
            metadata=self.helper_metadata(helper),
        )
        await resolve(
            ts=ticket.msg_ts,
            resolver=helper.slack_id,
            client=env.slack_client,
            send_resolved_message=False,
        )
