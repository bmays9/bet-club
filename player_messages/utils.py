# player_messages/utils.py
from .models import MessageTemplate, PlayerMessage
from django.utils.timezone import now


def create_message(code, context, group=None, receiver=None, actor=None, link=None):
    """
    Create PlayerMessage(s) using a MessageTemplate.

    Creates up to two messages per call:
    - A personal message to the receiver (audience="User")
      if template.template_self is set and receiver is provided
    - A group message (audience="Group")
      if template.template_group is set

    :param code: MessageTemplate code e.g. "LM-ENT"
    :param context: dict of placeholder values e.g. {"User": user, "league": "EPL"}
    :param group: UserGroup for group-audience messages
    :param receiver: User or list of Users for personal messages
    :param actor: User who triggered the action
    :param link: URL string override (uses template.game_link if not set)
    """
    try:
        template = MessageTemplate.objects.get(code=code)
    except MessageTemplate.DoesNotExist:
        # Silently skip unknown codes rather than crashing the calling view
        import logging
        logging.getLogger(__name__).warning(
            f"MessageTemplate with code '{code}' not found -- message not created."
        )
        return []

    # Build base context -- coerce User objects to usernames for template formatting
    ctx = {}
    for k, v in context.items():
        from django.contrib.auth.models import User
        ctx[k] = v.username if isinstance(v, User) else v

    if actor:
        ctx.setdefault("User", actor.username)

    messages_to_create = []
    resolve_link = link or template.game_link or ""

    # --- 1. Personal message(s) to receiver ---
    if receiver and template.template_self:
        receivers = receiver if isinstance(receiver, (list, tuple)) else [receiver]
        for r in receivers:
            personal_ctx = ctx.copy()
            personal_ctx["User"] = r.username  # "You" context
            try:
                message_text = template.template_self.format(**personal_ctx)
            except KeyError:
                message_text = template.template_self

            messages_to_create.append(PlayerMessage(
                group=group,
                receiver=r,
                actor=actor,
                code=code,
                audience="User",        # FIX: was always defaulting to "Group"
                message=message_text,
                link=resolve_link,
            ))

    # --- 2. Group-wide message ---
    # Only create group message if template audience is "Group"
    # Ignore template_group content entirely for User-audience templates
    group_template = (template.template_group or "").strip()
    if template.audience == "Group" and group_template and group_template.lower() != "none" and group:
        try:
            group_text = group_template.format(**ctx)
        except KeyError:
            group_text = group_template

        messages_to_create.append(PlayerMessage(
            group=group,
            receiver=None,
            actor=actor,
            code=code,
            audience="Group",           # FIX: explicitly set
            message=group_text,
            link=resolve_link,
        ))

    return PlayerMessage.objects.bulk_create(messages_to_create)