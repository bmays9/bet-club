from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import BankBalance
from groups.models import UserGroup  # adjust import if needed


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
    if selected_group:
        balances = (
            BankBalance.objects
            .filter(group=selected_group)
            .select_related("user")
            .order_by("-balance")
        )

    return render(request, "bank/money_list.html", {
        "user_groups": user_groups,
        "selected_group": selected_group,
        "balances": balances,
    })