from django.db import models
from django.contrib.auth.models import User
from groups.models import UserGroup

# Create your models here.
class PlayerMessage(models.Model):
    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE, related_name='user_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.TextField()	 
    game = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    message = models.TextField()  # can include 
    link = models.TextField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.group.name} | {self.receiver}.{self.type} | {self.game}"