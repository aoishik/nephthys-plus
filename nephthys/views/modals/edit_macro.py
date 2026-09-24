from nephthys.database.tables import Macro


def get_edit_macro_modal(macro: Macro | None = None) -> dict:
    is_edit = macro is not None
    checked = []
    if not is_edit or macro.resolve_ticket:
        checked.append("resolve_ticket")
    if is_edit and macro.can_run_on_closed:
        checked.append("can_run_on_closed")
    if is_edit and macro.post_as_helper:
        checked.append("post_as_helper")

    def option(value: str, text: str) -> dict:
        return {"text": {"type": "plain_text", "text": text}, "value": value}

    options = [
        option("resolve_ticket", "Resolves the ticket when run"),
        option("can_run_on_closed", "Can run on closed tickets"),
        option("post_as_helper", "post as helper"),
    ]

    return {
        "type": "modal",
        "callback_id": "macro_form",
        "private_metadata": str(macro.id) if is_edit else "",
        "title": {"type": "plain_text", "text": ":rac_info: macro"},
        "submit": {"type": "plain_text", "text": "Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "macro_name",
                "label": {"type": "plain_text", "text": "Name (without the ?)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "macro_name",
                    "initial_value": macro.name if is_edit else "",
                },
            },
            {
                "type": "input",
                "block_id": "macro_message",
                "label": {"type": "plain_text", "text": "Response (markdown)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "macro_message",
                    "multiline": True,
                    "initial_value": macro.message if is_edit else "",
                },
            },
            {
                "type": "input",
                "block_id": "macro_flags",
                "optional": True,
                "label": {"type": "plain_text", "text": "Options"},
                "element": {
                    "type": "checkboxes",
                    "action_id": "macro_flags",
                    "options": options,
                    **(
                        {
                            "initial_options": [
                                option
                                for option in options
                                if option["value"] in checked
                            ]
                        }
                        if checked
                        else {}
                    ),
                },
            },
        ],
    }
