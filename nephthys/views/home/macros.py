from nephthys.database.tables import Macro
from nephthys.database.tables import User
from nephthys.utils.env import env
from nephthys.views.home import AppHomeView
from nephthys.views.home.components.header import get_header


async def get_macros_view(user: User | None) -> dict:
    header = get_header(user, AppHomeView.MACROS)
    can_manage = bool(user and (user.helper or user.admin))

    macros = (
        await Macro.objects().where(Macro.program == env.program).order_by(Macro.name)
    )

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":rac_info: Macros for {env.program}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    ":rac_thumbs: here you can add, edit, and delete custom `?macros` helpers can run in ticket threads"
                    if can_manage
                    else ":rac_thumbs: note: you're not a helper, so you can only view macros"
                ),
            },
        },
        {"type": "divider"},
    ]

    if not macros:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":rac_nooo: no custom macros yet{', add one below' if can_manage else ''}",
                },
            }
        )

    for macro in macros:
        flags = []
        if not macro.resolve_ticket:
            flags.append("no-resolve")
        if macro.can_run_on_closed:
            flags.append("can-run-on-closed")
        if macro.post_as_helper:
            flags.append("post-as-helper")
        flag_str = f" `[{', '.join(flags)}]`" if flags else ""
        preview = macro.message[:200] + ("..." if len(macro.message) > 200 else "")
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*?{macro.name}*{flag_str}\n{preview}",
                },
            }
        )
        if can_manage:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": ":pencil2: edit"},
                            "action_id": "edit-macro",
                            "value": str(macro.id),
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": ":wastebasket: delete",
                            },
                            "action_id": "delete-macro",
                            "value": str(macro.id),
                            "style": "danger",
                            "confirm": {
                                "title": {
                                    "type": "plain_text",
                                    "text": "Delete macro?",
                                },
                                "text": {
                                    "type": "plain_text",
                                    "text": f"This will permanently delete ?{macro.name}.",
                                },
                                "confirm": {"type": "plain_text", "text": "Delete"},
                                "deny": {"type": "plain_text", "text": "Cancel"},
                            },
                        },
                    ],
                }
            )
        blocks.append({"type": "divider"})

    if can_manage:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": ":rac_cute: add a macro?",
                        },
                        "action_id": "add-macro",
                        "style": "primary",
                    }
                ],
            }
        )

    return {"type": "home", "blocks": [*header, *blocks]}
