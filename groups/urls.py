# groups/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_group, name='create_group'),
    path('join/', views.join_group, name='join_group'),
    path('my-groups/', views.my_groups, name='my_groups'),
    path('group/<int:group_id>/', views.group_home, name='group_home'),
]