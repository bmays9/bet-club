# player_messages/utils.py
from .models import MessageTemplate, PlayerMessage
from django.utils.timezone import now

def create_message(code, context, group=None, receiver=None, actor=None, link=None):
    """
    Create a PlayerMessage using a MessageTemplate.

    :param code: The template code (e.g. "LM-ENT")
    :param context: dict of replacements, e.g. {"User": user.username, "league": "Premier League"}
    :param group: optional group object (for group audience messages)
    :param receiver: optional user object (for personal audience messages)
    :param actor: the user who performed the action (to check if receiver == actor)
    :param link: override link if needed
    """
    try:
        template = MessageTemplate.objects.get(code=code)
    except MessageTemplate.DoesNotExist:
        raise ValueError(f"MessageTemplate with code {code} not found")
    
    # base context
    ctx = context.copy()
    if actor:
        ctx.setdefault("User", actor.username)
    if group:
        ctx.setdefault("league", getattr(group, "display_name", str(group)))
    
    messages = []

    # --- 1) Personal message(s) ---
    if receiver and template.template_self:
        receivers = receiver if isinstance(receiver, (list, tuple)) else [receiver]
        for r in receivers:
            personal_ctx = ctx.copy()
            personal_ctx["User"] = r.username  # overwrite User placeholder for "You"
            message = template.template_self.format(**personal_ctx)

            messages.append(PlayerMessage(
                group=group,
                receiver=r,
                code=code,
                message=message,
                link=link or template.game_link,
                created_at=now(),
            ))
        created_personal = True

    # --- 2) Group message ---
    if template.template_group:
        #skip if 
        group_message = template.template_group.format(**ctx)
        messages.append(PlayerMessage(
            group=group,
            receiver=None,
            code=code,
            message=group_message,
            link=link or template.game_link,
            created_at=now(),
        ))

    return PlayerMessage.objects.bulk_create(messages)
