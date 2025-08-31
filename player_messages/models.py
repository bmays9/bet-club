from django.db import models
from django.contrib.auth.models import User
from groups.models import UserGroup

# Create your models here.
class PlayerMessage(models.Model):
    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE, null=True, blank=True)
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    code = models.CharField(max_length=20)
    audience = models.CharField(   # ✅ key field
        max_length=10,
        choices=[("Group", "Group"), ("User", "User")],
        default="Group"
    )
    message = models.TextField()
    link = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.audience == "User":
            return f"{self.code} → {self.receiver} (personal)"
        return f"{self.code} → {self.group} (group)"


class MessageTemplate(models.Model):
    code = models.CharField(max_length=20, unique=True)
    inputs = models.CharField(max_length=200, blank=True)  # comma-separated list of required inputs
    audience = models.CharField(max_length=20, choices=[("User", "User"), ("Group", "Group")])
    template_group = models.TextField()  # "{User} has entered {league} LMS game"
    template_self = models.TextField(blank=True, null=True)  # "You have entered {league} LMS game"
    game_link = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return f"{self.code}"