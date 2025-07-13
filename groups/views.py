# groups/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import UserGroup
from .forms import CreateGroupForm, JoinGroupForm
from bank.models import BankBalance
import string, random

def generate_access_code(length):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@login_required
def create_group(request):
    if request.method == 'POST':
        form = CreateGroupForm(request.POST)
        if form.is_valid():
            group = form.save(commit=False)
            group.access_code = generate_access_code(6)
            group.created_by = request.user  # Set the required field
            group.save()

            # Add the creator as the first member
            group.members.add(request.user)

            # Create their zero balance
            BankBalance.objects.get_or_create(
                user=request.user,
                group=group,
                defaults={'balance': 0}
            )

            messages.success(request, f"Group '{group.name}' created!")
            return redirect('group_home', group_id=group.id)
    else:
        form = CreateGroupForm()
    
    return render(request, 'groups/create_group.html', {'form': form})

@login_required
def join_group(request):
    if request.method == 'POST':
        form = JoinGroupForm(request.POST)
        if form.is_valid():
            access_code = form.cleaned_data['access_code'].upper()
            try:
                group = UserGroup.objects.get(access_code=access_code)
                if request.user in group.members.all():
                    messages.warning(request, "You are already a member of this group.")
                else:
                    group.members.add(request.user)
                    
                    # ✅ Create a zero bank balance for this user in the group
                    BankBalance.objects.get_or_create(
                        user=request.user,
                        group=group,
                        defaults={'balance': 0}
                    )

                    messages.success(request, f"You've successfully joined {group.name}!")
                    return redirect('group_home', group_id=group.id)
            except UserGroup.DoesNotExist:
                messages.error(request, "Invalid access code.")
    else:
        form = JoinGroupForm()

    return render(request, 'groups/join_group.html', {'form': form})

@login_required
def my_groups(request):
    groups = request.user.joined_groups.all()
    return render(request, 'groups/my_groups.html', {'groups': groups})

@login_required
def group_home(request, group_id):
    group = get_object_or_404(UserGroup, id=group_id)

    # Get all users in the group and their balances
    balances = BankBalance.objects.filter(group=group).select_related('user').order_by('-balance')

    if request.user not in group.members.all():
        messages.error(request, "You are not a member of this group.")
        return redirect('my_groups')
    
    members = group.members.all()
    
    return render(request, 'groups/group_home.html', {
        'group': group,
        'balances': balances
    })

