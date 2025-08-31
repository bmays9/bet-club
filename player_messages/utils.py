# player_messages/utils.py
from .models import MessageTemplate, PlayerMessage

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

    # Pick which template to use
    if receiver and actor and receiver == actor and template.template_self:
        message_text = template.template_self.format(**context)
    else:
        message_text = template.template_group.format(**context)

    return PlayerMessage.objects.create(
        group=group,
        receiver=receiver,
        code=code,
        message=message_text,
        link=link or template.game_link
    )
