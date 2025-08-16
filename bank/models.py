# bank/models.py

from django.db import models
from django.contrib.auth.models import User
from groups.models import UserGroup  # ✅ Correct model name
from django.utils import timezone

class BankBalance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = ('user', 'group')  # ensures one balance per user per group

    def __str__(self):
        return f"{self.user.username} - {self.group.name}: £{self.balance}"


# bank/models.py
class BankTransactionBatch(models.Model):
    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.group.name} - {self.description} ({self.created_at:%Y-%m-%d %H:%M})"

class BankTransaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    transaction_type = models.CharField(max_length=10, choices=[('credit','Credit'),('debit','Debit')])
    batch = models.ForeignKey(BankTransactionBatch, on_delete=models.CASCADE, related_name="transactions")
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.username} {self.transaction_type} £{self.amount} ({self.created_at:%Y-%m-%d %H:%M})"

class BankMessage(models.Model):
    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE, related_name='bank_messages')
    created_at = models.DateTimeField(auto_now_add=True)
    message = models.TextField()  # can include 
    link = models.TextField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.group.name} - {self.created_at}: {self.message[:50]}"