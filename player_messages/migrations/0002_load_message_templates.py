from django.db import migrations

# player_messages/migrations/0002_load_message_templates.py

def add_templates(apps, schema_editor):
    MessageTemplate = apps.get_model("player_messages", "MessageTemplate")
    
    templates = [
        dict(
            code="SP-ENT",
            audience="Group",
            template_group="{User} has entered Score Predict",
            template_self="You have entered Score Predict",
        ),
        dict(
            code="SP-WIN",
            audience="Group",
            template_group="{User} has won £{prize} on Score Predict with a score of {score}!",
            template_self="You have won £{prize} on Score Predict with a score of {score}!",
        ),
        dict(
            code="LM-NEW",
            audience="Group",
            template_group="A new {league} LMS game is open for you to join",
            template_self="You have created a new {league} LMS game",
        ),
        dict(
            code="LM-ENT",
            audience="Group",
            template_group="{User} has entered {league} LMS game",
            template_self="You have entered {league} LMS game",
        ),
        dict(
            code="LM-REM",
            audience="User",
            template_group="None",
            template_self="You have not yet made your {league} LMS pick for round {round}",
        ),
        dict(
            code="LM-VIS",
            audience="Group",
            template_group="LMS picks are now visible for {league}",
            template_self="None",
        ),
        dict(
            code="LM-PCK",
            audience="Group",
            template_group="{User} has made their {league} LMS pick in round {round}",
            template_self="You have entered {league} LMS game",
        ),
        dict(
            code="LM-UKO",
            audience="Group",
            template_group="{User} has been knocked out of {league} LMS",
            template_self="You have been knocked out of {league} LMS",
        ),
        dict(
            code="LM-UWN",
            audience="Group",
            template_group="{User} has picked a winner and is through to the next round of {league} LMS",
            template_self="Good news! You picked a winner in {league} LMS and are through to the next round",
        ),
        dict(
            code="LM-RCM",
            audience="Group",
            template_group="{league} LMS Round is complete. {alive} of {entrants} remain",
            template_self="None",
        ),
        dict(
            code="LM-WIN",
            audience="Group",
            template_group="{User} is the last man standing in {league}! They have won {prize}",
            template_self="None",
        ),
        dict(
            code="LM-OOO",
            audience="Group",
            template_group="No players are left standing in {league}! The {prize} pot will rollover to the next game",
            template_self="None",
        ),
    ]

    for t in templates:
        MessageTemplate.objects.update_or_create(code=t["code"], defaults=t)

def remove_templates(apps, schema_editor):
    MessageTemplate = apps.get_model("player_messages", "MessageTemplate")
    codes = [
        "SP-ENT",
        "SP-WIN",
        "LM-NEW",
        "LM-ENT",
        "LM-REM",
        "LM-VIS",
        "LM-PCK",
        "LM-UKO",
        "LM-UWN",
        "LM-RCM",
        "LM-WIN",
        "LM-OOO",
        "LM-REM",
        "LM-VIS",
        "LM-PCK",
        "LM-UKO",
        "LM-UWN",
        "LM-RCM",
        "LM-WIN",
        "LM-OOO"
    ]  # keep in sync
    MessageTemplate.objects.filter(code__in=codes).delete()

class Migration(migrations.Migration):
    dependencies = [
        ("player_messages", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_templates, remove_templates),
    ]