from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import (
    BankBalance, BankTransaction, BankTransactionBatch,
    BankMessage, RealMoneyPayment,
)
from .services import apply_batch
from player_messages.utils import create_message


# -------------------------------------------------------
# apply_batch (unchanged core logic)
# -------------------------------------------------------

# apply_batch imported from bank.services above

# -------------------------------------------------------
# P&L helpers
# -------------------------------------------------------

def get_game_pnl(user, group):
    """
    Returns net P&L per game type for a user in a group.
    Calculated from BankTransaction records created by apply_batch.
    Only reflects games that have been fully settled (apply_batch called).
    Games where check_for_winners has not yet run will show GBP0.
    """
    # Keywords in batch descriptions to categorise
    CATEGORIES = {
        "Score Predict": ["Score Predict", "score predict"],
        "LMS": ["LMS", "Last Man Standing"],
        "Golf": ["Golf", "golf"],
        "Season": ["Season", "season"],
        "Cash": ["Cash payment", "cash payment"],
    }

    result = {}

    for label, keywords in CATEGORIES.items():
        q = Q()
        for kw in keywords:
            q |= Q(batch__description__icontains=kw)

        transactions = BankTransaction.objects.filter(
            user=user, batch__group=group
        ).filter(q)

        credits = transactions.filter(
            transaction_type=BankTransaction.CREDIT
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        debits = transactions.filter(
            transaction_type=BankTransaction.DEBIT
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        net = credits - debits
        result[label] = {
            "credits": credits,
            "debits": debits,
            "net": net,
        }

    return result


# -------------------------------------------------------
# Money list view
# -------------------------------------------------------

@login_required
def money_list(request):
    user = request.user
    user_groups = user.joined_groups.all()

    group_id = request.GET.get("group")
    selected_group = (
        user_groups.filter(id=group_id).first() if group_id
        else user_groups.first()
    )

    balances = []
    player_messages_list = []
    bank_messages = []
    my_pnl = {}
    my_balance = None
    pending_incoming = []
    pending_outgoing = []


    if selected_group:
        # All balances for leaderboard (visible to all)
        balances = (
            BankBalance.objects
            .filter(group=selected_group)
            .select_related("user")
            .order_by("-balance")
        )

        # Current user's balance
        my_balance = balances.filter(user=user).first()

        # Player messages for this group
        from player_messages.models import PlayerMessage
        player_messages_list = (
            PlayerMessage.objects
            .filter(group=selected_group)
            .filter(Q(audience="Group") | Q(receiver=user))
            .order_by("-created_at")[:20]
        )

        # Bank transaction messages
        bank_messages = (
            BankMessage.objects
            .filter(group=selected_group)
            .order_by("-created_at")[:10]
        )

        # My P&L breakdown (private)
        my_pnl = get_game_pnl(user, selected_group)

        # Real money payments
        # Pending payments needing my action
        pending_incoming = RealMoneyPayment.objects.filter(
            group=selected_group,
            receiver=user,
            status=RealMoneyPayment.STATUS_PENDING,
        ).select_related("payer")

        pending_outgoing = RealMoneyPayment.objects.filter(
            group=selected_group,
            payer=user,
            status=RealMoneyPayment.STATUS_PENDING,
        ).select_related("receiver")

    # Group members for payment form
    group_members = []
    if selected_group:
        group_members = selected_group.members.exclude(id=user.id)

    return render(request, "bank/money_list.html", {
        "user_groups": user_groups,
        "selected_group": selected_group,
        "balances": balances,
        "my_balance": my_balance,
        "player_messages": player_messages_list,
        "bank_messages": bank_messages,
        "my_pnl": my_pnl,
        "pending_incoming": pending_incoming,
        "pending_outgoing": pending_outgoing,
        "group_members": group_members,
    })


# -------------------------------------------------------
# Make a payment
# -------------------------------------------------------

@login_required
def make_payment(request):
    if request.method != "POST":
        return redirect("index")

    group_id = request.POST.get("group_id")
    receiver_id = request.POST.get("receiver_id")
    amount_str = request.POST.get("amount", "").strip()
    note = request.POST.get("note", "").strip()

    group = get_object_or_404(
        request.user.joined_groups.all(), id=group_id
    )
    receiver = get_object_or_404(
        group.members.exclude(id=request.user.id), id=receiver_id
    )

    try:
        amount = Decimal(amount_str).quantize(Decimal("0.01"))
        if amount <= 0:
            raise ValueError
    except Exception:
        messages.error(request, "Please enter a valid amount.")
        return redirect(f"/bank/?group={group_id}")

    payment = RealMoneyPayment.objects.create(
        group=group,
        payer=request.user,
        receiver=receiver,
        amount=amount,
        note=note,
    )

    # Notify both players
    create_message(
        code="PAY-SENT",
        context={
            "User": request.user,
            "receiver": receiver.username,
            "amount": f"{amount:.2f}",
            "note": note or "no note",
        },
        group=group,
        receiver=request.user,
        actor=request.user,
        link="index",
    )
    create_message(
        code="PAY-RECV",
        context={
            "User": request.user,
            "amount": f"{amount:.2f}",
            "note": note or "no note",
        },
        group=group,
        receiver=receiver,
        actor=request.user,
        link="index",
    )

    messages.success(
        request,
        f"Payment of GBP{amount:.2f} to {receiver.username} recorded. "
        f"Awaiting their confirmation."
    )
    return redirect(f"/?group={group.id}")


# -------------------------------------------------------
# Confirm a payment (receiver action)
# -------------------------------------------------------

@login_required
def confirm_payment(request, payment_id):
    payment = get_object_or_404(
        RealMoneyPayment,
        id=payment_id,
        receiver=request.user,
        status=RealMoneyPayment.STATUS_PENDING,
    )

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "confirm":
            with transaction.atomic():
                payment.status = RealMoneyPayment.STATUS_CONFIRMED
                payment.resolved_at = timezone.now()
                payment.save(update_fields=["status", "resolved_at"])

                # Apply balance changes
                description = (
                    f"Cash payment: {payment.payer.username} -> "
                    f"{payment.receiver.username}"
                    + (f" ({payment.note})" if payment.note else "")
                )
                apply_batch(
                    group=payment.group,
                    entrants=[payment.payer],
                    winners=[payment.receiver],
                    entry_fee=payment.amount,
                    prize_pool=payment.amount,
                    description=description,
                )

            # Messages
            create_message(
                code="PAY-CONF",
                context={
                    "User": payment.receiver,
                    "payer": payment.payer.username,
                    "amount": f"{payment.amount:.2f}",
                },
                group=payment.group,
                receiver=payment.payer,
                actor=payment.receiver,
                link="index",
            )
            messages.success(
                request,
                f"Payment of GBP{payment.amount:.2f} from "
                f"{payment.payer.username} confirmed. Balances updated."
            )

        elif action == "reject":
            payment.status = RealMoneyPayment.STATUS_REJECTED
            payment.resolved_at = timezone.now()
            payment.save(update_fields=["status", "resolved_at"])

            create_message(
                code="PAY-REJ",
                context={
                    "User": payment.receiver,
                    "amount": f"{payment.amount:.2f}",
                },
                group=payment.group,
                receiver=payment.payer,
                actor=payment.receiver,
                link="index",
            )
            messages.warning(
                request,
                f"Payment rejected. {payment.payer.username} has been notified."
            )

    return redirect(f"/?group={payment.group_id}")


# -------------------------------------------------------
# Cancel a payment (payer action)
# -------------------------------------------------------

@login_required
def cancel_payment(request, payment_id):
    payment = get_object_or_404(
        RealMoneyPayment,
        id=payment_id,
        payer=request.user,
        status=RealMoneyPayment.STATUS_PENDING,
    )
    if request.method == "POST":
        payment.status = RealMoneyPayment.STATUS_CANCELLED
        payment.resolved_at = timezone.now()
        payment.save(update_fields=["status", "resolved_at"])
        messages.info(request, "Payment cancelled.")
    return redirect(f"/?group={payment.group_id}")
