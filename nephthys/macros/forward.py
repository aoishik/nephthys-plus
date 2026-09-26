import asyncio
import logging
import re
from typing import Any
from typing import cast

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from nephthys.actions.resolve import resolve
from nephthys.database.tables import Ticket
from nephthys.database.tables import User
from nephthys.macros.types import Macro
from nephthys.utils.env import env
from nephthys.utils.slack_user import get_user_profile
from nephthys.utils.ticket_methods import reply_to_ticket

FORWARD_EVENT_TYPE = "nephthys_plus_forward"
FORWARD_REPLY_EVENT_TYPE = "nephthys_plus_forward_reply"
CHANNEL_PATTERN = re.compile(
    r"^\?forward\s+(?:#([a-z0-9_-]+)|<#([A-Z0-9]+)(?:\|([^>]*))?>)$",
    re.IGNORECASE,
)


def parse_forward_target(text: str) -> tuple[str, str | None] | None:
    match = CHANNEL_PATTERN.fullmatch(text.strip())
    if not match:
        return None
    if match.group(2):
        return match.group(2), match.group(3) or None
    return match.group(1), None


def is_current_bot(
    message: dict[str, Any], bot_user_id: str | None, bot_id: str | None
) -> bool:
    return bool(
        (bot_user_id and message.get("user") == bot_user_id)
        or (bot_id and message.get("bot_id") == bot_id)
    )


async def resolve_channel(client: AsyncWebClient, reference: str) -> dict[str, Any]:
    if reference.startswith(("C", "G")):
        response = await client.conversations_info(channel=reference)
        channel = cast(dict[str, Any], response["channel"])
        if not channel:
            raise ValueError(f"Could not find Slack channel {reference}")
        return channel

    response = await client.conversations_list(
        exclude_archived=True,
        types="public_channel,private_channel",
        limit=1000,
    )
    for channel in response.get("channels", []):
        if channel.get("name", "").casefold() == reference.casefold():
            return channel
    raise ValueError(f"Could not find Slack channel #{reference}")


async def send_forward_error(ticket: Ticket, helper: User, message: str) -> None:
    await env.slack_client.chat_postEphemeral(
        channel=env.slack_help_channel,
        thread_ts=ticket.msg_ts,
        user=helper.slack_id,
        text=message,
    )


async def get_message_identity(message: dict[str, Any]) -> tuple[str, str | None]:
    author_id = message.get("user") or message.get("bot_id")
    if not author_id:
        return "Unknown user", None
    try:
        profile = await get_user_profile(author_id)
    except Exception:
        logging.warning("Could not load Slack profile for %s", author_id, exc_info=True)
        return message.get("username") or author_id, None
    return profile.display_name(), profile.profile_pic_512x()


async def copy_forwarded_replies(
    client: AsyncWebClient,
    messages: list[dict[str, Any]],
    destination_channel: str,
    destination_ts: str,
    source_ts: str,
    bot_user_id: str | None,
    bot_id: str | None,
) -> None:
    for message in messages:
        if message.get("ts") == source_ts:
            continue
        if is_current_bot(message, bot_user_id, bot_id):
            continue
        if (message.get("text") or "").lstrip().startswith("?"):
            continue

        author_id = message.get("user") or message.get("bot_id")
        if not author_id:
            continue
        username, icon_url = await get_message_identity(message)
        await client.chat_postMessage(
            channel=destination_channel,
            thread_ts=destination_ts,
            text=message.get("text") or " ",
            blocks=message.get("blocks"),
            attachments=message.get("attachments"),
            username=username,
            icon_url=icon_url,
            metadata={
                "event_type": FORWARD_REPLY_EVENT_TYPE,
                "event_payload": {"source_user_id": author_id},
            },
            unfurl_links=True,
            unfurl_media=True,
        )


class Forward(Macro):
    name = "forward"

    async def run(self, ticket: Ticket, helper: User, **kwargs: Any) -> None:
        target = parse_forward_target(kwargs.get("text", ""))
        if not target:
            await send_forward_error(ticket, helper, "Usage: `?forward #channel`")
            return

        channel_reference, channel_name = target
        client = env.slack_client
        try:
            bot_info = await client.auth_test()
            bot_user_id = bot_info.get("user_id")
            bot_id = bot_info.get("bot_id")
            history = await client.conversations_replies(
                channel=env.slack_help_channel,
                ts=ticket.msg_ts,
                limit=200,
            )
            messages = history.get("messages", [])
            source_message = next(
                (message for message in messages if message.get("ts") == ticket.msg_ts),
                None,
            )
            if not source_message or not source_message.get("text"):
                raise ValueError("The original ticket message could not be found")

            destination = await resolve_channel(client, channel_reference)
            destination_channel = destination["id"]
            destination_name = (
                destination.get("name") or channel_name or channel_reference
            )
            source_user_id = ticket.opened_by.slack_id
            source_profile = await get_user_profile(source_user_id)
            destination_message = await client.chat_postMessage(
                channel=destination_channel,
                text=source_message["text"],
                blocks=source_message.get("blocks"),
                attachments=source_message.get("attachments"),
                username=source_profile.display_name(),
                icon_url=source_profile.profile_pic_512x(),
                metadata={
                    "event_type": FORWARD_EVENT_TYPE,
                    "event_payload": {
                        "source_user_id": source_user_id,
                        "ticket": True,
                    },
                },
                unfurl_links=True,
                unfurl_media=True,
            )
            destination_payload = cast(dict[str, Any], destination_message["message"])
            destination_ts = destination_payload.get("ts")
            if not isinstance(destination_ts, str):
                raise ValueError("Slack did not return a forwarded message timestamp")
            destination_link = (
                f"https://hackclub.slack.com/archives/{destination_channel}/"
                f"p{destination_ts.replace('.', '')}"
            )
            helper_profile = await get_user_profile(helper.slack_id)
            await reply_to_ticket(
                ticket=ticket,
                client=client,
                text=(
                    f"Forwarded to #{destination_name}, <{destination_link}|message>"
                ),
                username=helper_profile.display_name(),
                icon_url=helper_profile.profile_pic_512x(),
                metadata={
                    "event_type": "nephthys_macro_reply",
                    "event_payload": {"source_user_id": helper.slack_id},
                },
            )
            await resolve(
                ts=ticket.msg_ts,
                resolver=helper.slack_id,
                client=client,
                send_resolved_message=False,
            )
            await asyncio.sleep(1)
            await copy_forwarded_replies(
                client=client,
                messages=messages,
                destination_channel=destination_channel,
                destination_ts=destination_ts,
                source_ts=ticket.msg_ts,
                bot_user_id=bot_user_id,
                bot_id=bot_id,
            )
        except (SlackApiError, ValueError) as error:
            logging.warning("Could not forward ticket: %s", error)
            await send_forward_error(ticket, helper, str(error))
