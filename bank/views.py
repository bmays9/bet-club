from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Exists, OuterRef
from .models import BankBalance, BankMessage
from player_messages.models import PlayerMessage
from groups.models import UserGroup


def money_list(request):
    if not request.user.is_authenticated:
        # Option 1: Redirect to login page
        # return redirect('login')

        # Option 2: Or just show empty page or message
        return render(request, "bank/money_list.html", {
            "user_groups": [],
            "selected_group": None,
            "balances": [],
            "not_logged_in": True,
        })

    user_groups = UserGroup.objects.filter(members=request.user)  # or your relation logic
    selected_group_id = request.GET.get("group")

    # Default to first group if none selected
    if selected_group_id:
        selected_group = user_groups.filter(id=selected_group_id).first()
    else:
        selected_group = user_groups.first()

    balances = []
    messages = []
    if selected_group:
        # Ensure every group member has a BankBalance
        for member in selected_group.members.all():
            BankBalance.objects.get_or_create(user=member, group=selected_group, defaults={'balance': 0})

        balances = (
            BankBalance.objects
            .filter(group=selected_group)
            .select_related("user")
            .order_by("-balance")
        )

        bank_messages = (
            BankMessage.objects
            .filter(group=selected_group)
            .order_by("-created_at")[:20]  # 👈 newest 20
        )

        # Personal and group messages merged
        personal_messages = PlayerMessage.objects.filter(
            group=selected_group,
            receiver=request.user
        )

        print("Personal", personal_messages)

        overlap = PlayerMessage.objects.filter(
            group=selected_group,
            receiver=request.user,
            actor=OuterRef("actor"),
            code=OuterRef("code")
        )

        group_messages = PlayerMessage.objects.filter(
            group=selected_group,
            receiver__isnull=True
        ).exclude(Exists(overlap))
        
        print("group_messages", group_messages)

        unfiltered_group_messages = PlayerMessage.objects.filter(
            group=selected_group,
            receiver__isnull=True
        )
        
        print("unfiltered_group_messages", unfiltered_group_messages)

        player_messages = personal_messages.union(group_messages).order_by("-created_at")[:20]

        print("Player Messages", player_messages)

    return render(request, "bank/money_list.html", {
        "user_groups": user_groups,
        "selected_group": selected_group,
        "balances": balances,
        "bank_messages": bank_messages,  
        "player_messages": player_messages,  
    })