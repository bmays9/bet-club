# bank/models.py

from django.db import models
from django.contrib.auth.models import User
from groups.models import UserGroup  # ✅ Correct model name

class BankBalance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = ('user', 'group')  # ensures one balance per user per group

    def __str__(self):
        return f"{self.user.username} - {self.group.name}: £{self.balance}"
