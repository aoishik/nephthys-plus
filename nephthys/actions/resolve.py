import logging
from datetime import datetime
from datetime import UTC

from blockkit import Actions
from blockkit import Button
from blockkit import Section
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from nephthys.database.enums import TicketStatus
from nephthys.database.tables import Ticket
from nephthys.database.tables import User
from nephthys.utils.ai import decisions
from nephthys.utils.delete_thread import add_thread_to_delete_queue
from nephthys.utils.env import env
from nephthys.utils.logging import send_heartbeat
from nephthys.utils.permissions import can_resolve
from nephthys.utils.ticket_methods import delete_message
from nephthys.utils.ticket_methods import reply_to_ticket


NO_CREDIT = "none"


async def resolve(
    ts: str,
    resolver: str,
    client: AsyncWebClient,
    stale: bool = False,
    add_reaction: bool = True,
    send_resolved_message: bool = True,
):
    resolving_user = await User.objects().where(User.slack_id == resolver).first()
    if not resolving_user:
        await send_heartbeat(
            f"User {resolver} attempted to resolve ticket with ts {ts} but isn't in the database.",
            messages=[f"Ticket TS: {ts}", f"Resolver ID: {resolver}"],
        )
        return

    allowed = await can_resolve(resolving_user.slack_id, resolving_user.id, ts)
    if not allowed:
        await send_heartbeat(
            f"User {resolver} attempted to resolve ticket with ts {ts} without permission.",
            messages=[f"Ticket TS: {ts}", f"Resolver ID: {resolver}"],
        )
        await client.chat_postEphemeral(
            channel=env.slack_help_channel,
            thread_ts=ts,
            user=resolver,
            text="Only helpers or the original poster can mark this thread as resolved.",
        )
        return

    ticket = await Ticket.objects(Ticket.assigned_to, Ticket.opened_by).get(
        (Ticket.msg_ts == ts)
    )
    if not ticket:
        raise ValueError(f"Failed to find ticket with ts {ts}")
    if ticket.status == TicketStatus.CLOSED:
        await client.chat_postEphemeral(
            channel=env.slack_help_channel,
            thread_ts=ticket.msg_ts,
            user=resolver,
            text="Cannot mark as resolved — this ticket is already resolved!",
        )
        return

    now = datetime.now(UTC)
    credit_user = None
    jev_decided = False
    try:
        replies = await env.slack_client.conversations_replies(
            channel=env.slack_help_channel,
            ts=ticket.msg_ts,
            include_all_metadata=True,
            limit=500,
        )
        thread = []
        for msg in replies["messages"][1:]:
            metadata = msg.get("metadata") or {}
            author = None
            if metadata.get("event_type") == "nephthys_macro_reply":
                author = (metadata.get("event_payload") or {}).get("source_user_id")
            elif not msg.get("bot_id"):
                author = msg.get("user")
            if author:
                thread.append({"author": author, "text": msg.get("text") or ""})
        participants = {m["author"] for m in thread} | {resolving_user.slack_id}
        participants.discard(ticket.opened_by.slack_id)

        # is_in([]) raises, e.g. when the author resolves their own ticket
        candidate = (
            await User.objects().where(
                User.slack_id.is_in(list(participants)) & User.helper.eq(True)
            )
            if participants
            else []
        )
        if len(candidate) == 1:
            credit_user = candidate[0]
        elif len(candidate) > 1:
            response = await decisions(
                model=env.ai_credit_model,
                state={
                    "question": {
                        "title": ticket.title,
                        "description": ticket.description,
                    },
                    "replies": thread,
                },
                questions={
                    "credit": {
                        "type": "choice",
                        "instructions": (
                            "Credit the helper whose reply actually answered or solved the "
                            "poster's question. An answer counts even if the poster never "
                            "replied, thanked anyone, or left the channel: silence is not "
                            "failure. A helper with 0 replies only closed the thread and "
                            "gets credit only if no one else helped. Choose 'none' only if "
                            "the ticket is a test, spam or nonsense, or no helper gave a "
                            "substantive answer."
                        ),
                        "criteria": {
                            **{
                                c.slack_id: (
                                    f"{c.username or c.slack_id}: "
                                    f"{sum(1 for m in thread if m['author'] == c.slack_id)} replies"
                                )
                                for c in candidate
                            },
                            NO_CREDIT: "No one: test/spam/nonsense ticket, or no helper gave a real answer (NOT for answered questions the poster just never followed up on)",
                        },
                    }
                },
            )
            choice = response["answers"]["credit"]["choice"]
            credit_user = next((c for c in candidate if c.slack_id == choice), None)
            jev_decided = True
    except Exception as e:
        logging.error(f"Failed to pick credit user: {e}", exc_info=True)
    await Ticket.update(
        {
            Ticket.status: TicketStatus.CLOSED,
            Ticket.closed_by: credit_user.id if credit_user else None,
            Ticket.closed_at: now,
        }
    ).where(Ticket.msg_ts == ts)

    tkt = await Ticket.objects().where(Ticket.msg_ts == ts).first()
    if not tkt:
        await send_heartbeat(
            f"Failed to resolve ticket with ts {ts} by {resolver}. Ticket not found.",
            messages=[f"Ticket TS: {ts}", f"Resolver ID: {resolver}"],
        )
        return

    # Build the "ticket resolved!" message
    text = (
        env.transcript.ticket_resolve.format(user_id=resolving_user.slack_id)
        if not stale
        else env.transcript.ticket_resolve_stale.format(user_id=resolving_user.slack_id)
    )
    actions = Actions()
    if env.enable_feedback:
        actions.add_element(
            Button(
                text="Give feedback",
                action_id="feedback-button",
                value=f"{tkt.id}",
            )
        )
    actions.add_element(
        Button(
            text="Re-open thread",
            action_id="reopen-button",
            value=f"{tkt.id}",
        )
    )

    if send_resolved_message:
        await reply_to_ticket(
            ticket=tkt,
            client=client,
            text=text,
            blocks=[Section(text), actions],
        )
    if jev_decided and resolving_user.helper:
        if credit_user is None:
            note = "Jev :tm: decided that no one gets credit for this one."
        elif credit_user.slack_id != resolving_user.slack_id:
            note = f"nice try stealing that ticket, but Jev :tm: decided that <@{credit_user.slack_id}> will get the credit."
        else:
            note = None
        if note:
            await client.chat_postEphemeral(
                channel=env.slack_help_channel,
                thread_ts=ts,
                user=resolving_user.slack_id,
                text=note,
            )
    if add_reaction:
        await client.reactions_add(
            channel=env.slack_help_channel,
            name="white_check_mark",
            timestamp=ts,
        )

    try:
        await client.reactions_remove(
            channel=env.slack_help_channel,
            name="thinking_face",
            timestamp=ts,
        )
    except SlackApiError as e:
        logging.error(
            f"Failed to remove thinking reaction from ticket with ts {ts}: {e.response['error']}"
        )

    if await env.workspace_admin_available():
        await add_thread_to_delete_queue(
            channel_id=env.slack_ticket_channel, thread_ts=tkt.ticket_ts
        )
    else:
        await delete_message(
            channel_id=env.slack_ticket_channel, message_ts=tkt.ticket_ts
        )

    logging.info(
        f"Resolved ticket ts={ts} by slack_id={resolving_user.slack_id} credit_to={credit_user.slack_id if credit_user else None}"
    )
