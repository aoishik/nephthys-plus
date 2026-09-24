import logging
from typing import Any
from typing import Dict

from slack_bolt.context.ack.async_ack import AsyncAck
from slack_sdk.web.async_client import AsyncWebClient

from nephthys.database.tables import Macro
from nephthys.database.tables import User
from nephthys.events.app_home_opened import open_app_home
from nephthys.utils.env import env
from nephthys.views.home import AppHomeView
from nephthys.views.modals.edit_macro import get_edit_macro_modal


async def _is_authorized(slack_id: str) -> bool:
    user = await User.objects().where(User.slack_id == slack_id).first()
    return bool(user and (user.helper or user.admin))


async def open_add_macro_modal(
    ack: AsyncAck, body: Dict[str, Any], client: AsyncWebClient
) -> None:
    await ack()
    user_id = body["user"]["id"]
    if not await _is_authorized(user_id):
        return
    await client.views_open(trigger_id=body["trigger_id"], view=get_edit_macro_modal())


async def open_edit_macro_modal(
    ack: AsyncAck, body: Dict[str, Any], client: AsyncWebClient
) -> None:
    await ack()
    user_id = body["user"]["id"]
    if not await _is_authorized(user_id):
        return
    macro_id = int(body["actions"][0]["value"])
    macro = (
        await Macro.objects()
        .where((Macro.id == macro_id) & (Macro.program == env.program))
        .first()
    )
    if not macro:
        return
    await client.views_open(
        trigger_id=body["trigger_id"], view=get_edit_macro_modal(macro)
    )


async def delete_macro_callback(
    ack: AsyncAck, body: Dict[str, Any], client: AsyncWebClient
) -> None:
    await ack()
    user_id = body["user"]["id"]
    if not await _is_authorized(user_id):
        return
    macro_id = int(body["actions"][0]["value"])
    await Macro.delete().where((Macro.id == macro_id) & (Macro.program == env.program))
    logging.info(
        f"Macro id={macro_id} deleted by <@{user_id}> for program {env.program}"
    )
    await open_app_home(AppHomeView.MACROS, client, user_id)


async def macro_form_view_callback(
    ack: AsyncAck, body: Dict[str, Any], client: AsyncWebClient
) -> None:
    user_id = body["user"]["id"]
    if not await _is_authorized(user_id):
        await ack()
        return

    values = body["view"]["state"]["values"]
    name = values["macro_name"]["macro_name"]["value"].strip().lstrip("?").lower()
    message = values["macro_message"]["macro_message"]["value"].strip()
    selected = {
        option["value"]
        for option in values["macro_flags"]["macro_flags"].get("selected_options") or []
    }

    if not name or not message:
        await ack(
            response_action="errors",
            errors={"macro_name": "Please provide a name and a response."},
        )
        return

    macro_id = body["view"]["private_metadata"]
    existing = (
        await Macro.objects()
        .where((Macro.name == name) & (Macro.program == env.program))
        .first()
    )
    if existing and str(existing.id) != macro_id:
        await ack(
            response_action="errors",
            errors={"macro_name": f"A macro named ?{name} already exists."},
        )
        return

    await ack()

    resolve_ticket = "resolve_ticket" in selected
    can_run_on_closed = "can_run_on_closed" in selected
    post_as_helper = "post_as_helper" in selected

    if macro_id:
        await Macro.update(
            {
                Macro.name: name,
                Macro.message: message,
                Macro.resolve_ticket: resolve_ticket,
                Macro.can_run_on_closed: can_run_on_closed,
                Macro.post_as_helper: post_as_helper,
            }
        ).where((Macro.id == int(macro_id)) & (Macro.program == env.program))
        logging.info(
            f"Macro '?{name}' updated by <@{user_id}> for program {env.program}"
        )
    else:
        await Macro(
            name=name,
            message=message,
            resolve_ticket=resolve_ticket,
            can_run_on_closed=can_run_on_closed,
            post_as_helper=post_as_helper,
            program=env.program,
        ).save()
        logging.info(f"Macro '?{name}' added by <@{user_id}> for program {env.program}")

    await open_app_home(AppHomeView.MACROS, client, user_id)
