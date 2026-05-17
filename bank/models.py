# bank/models.py
from django.db import models
from django.contrib.auth.models import User
from groups.models import UserGroup
from django.utils import timezone


class BankBalance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = ('user', 'group')

    def __str__(self):
        return f"{self.user.username} - {self.group.name}: GBP{self.balance}"


class BankTransactionBatch(models.Model):
    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.group.name} - {self.description} ({self.created_at:%Y-%m-%d %H:%M})"


class BankTransaction(models.Model):
    CREDIT = 'credit'
    DEBIT = 'debit'
    TRANSACTION_TYPES = [
        (CREDIT, 'Credit'),
        (DEBIT, 'Debit'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    batch = models.ForeignKey(
        BankTransactionBatch, on_delete=models.CASCADE, related_name="transactions"
    )
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return (
            f"{self.user.username} {self.transaction_type} "
            f"GBP{self.amount} ({self.created_at:%Y-%m-%d %H:%M})"
        )


class BankMessage(models.Model):
    group = models.ForeignKey(
        UserGroup, on_delete=models.CASCADE, related_name='bank_messages'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    message = models.TextField()
    link = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.group.name} - {self.created_at}: {self.message[:50]}"


class RealMoneyPayment(models.Model):
    """
    Records a real-world cash payment from one player to another.
    Balance adjustments only happen once the receiver confirms.
    """
    STATUS_PENDING = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_REJECTED = 'rejected'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending confirmation'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    group = models.ForeignKey(
        UserGroup, on_delete=models.CASCADE, related_name='real_payments'
    )
    payer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='payments_made'
    )
    receiver = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='payments_received'
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return (
            f"{self.payer.username} -> {self.receiver.username}: "
            f"GBP{self.amount} [{self.status}]"
        )
