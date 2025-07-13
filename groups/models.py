# groups/models.py
import random
import string
from django.db import models
from django.contrib.auth.models import User

def generate_unique_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not UserGroup.objects.filter(access_code=code).exists():
            return code

class UserGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    access_code = models.CharField(max_length=6, unique=True, editable=False)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_groups')
    members = models.ManyToManyField(User, related_name='joined_groups', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.access_code:
            self.access_code = generate_unique_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

