from decimal import Decimal, ROUND_DOWN
import random
from django.db import transaction
from .models import BankBalance, BankTransaction, BankTransactionBatch


def apply_batch(group, entrants=None, winners=None, entry_fee=Decimal("0"), prize_pool=Decimal("0"), description="Game"):
    """
    Process entrants (debits) + winners (credits) in a single atomic batch.
    """
    entrants = entrants or []
    winners = winners or []

    with transaction.atomic():
        batch = BankTransactionBatch.objects.create(group=group, description=description)

        # 1. Deduct entry fees
        for user in entrants:
            balance_obj, _ = BankBalance.objects.select_for_update().get_or_create(
                user=user, group=group, defaults={"balance": 0}
            )
            balance_obj.balance -= entry_fee
            balance_obj.save()

            BankTransaction.objects.create(
                user=user,
                transaction_type=BankTransaction.DEBIT,
                amount=entry_fee,
                batch=batch
            )

        # 2. Distribute winnings
        if winners and prize_pool > 0:
            share = (prize_pool / len(winners)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            total_distributed = share * len(winners)
            remainder = (prize_pool - total_distributed).quantize(Decimal("0.01"))

            winners_list = list(winners)
            random.shuffle(winners_list)

            for i, user in enumerate(winners_list):
                payout = share
                if remainder > 0:
                    payout += Decimal("0.01")
                    remainder -= Decimal("0.01")

                balance_obj, _ = BankBalance.objects.select_for_update().get_or_create(
                    user=user, group=group, defaults={"balance": 0}
                )
                balance_obj.balance += payout
                balance_obj.save()

                BankTransaction.objects.create(
                    user=user,
                    transaction_type=BankTransaction.CREDIT,
                    amount=payout,
                    batch=batch
                )

        return batch
