from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def baht_to_satang(value):
    try:
        amount = Decimal(str(value or "0"))
    except InvalidOperation as exc:
        raise ValueError("จำนวนเงินไม่ถูกต้อง") from exc
    if amount < 0:
        raise ValueError("จำนวนเงินต้องไม่ติดลบ")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def satang_to_baht(value):
    return f"{Decimal(int(value)) / 100:.2f}"


def change_breakdown(change_satang):
    if change_satang < 0:
        raise ValueError("เงินที่รับน้อยกว่ายอดชำระ")
    whole_baht, remaining_satang = divmod(change_satang, 100)
    denominations = []
    for value in (1000, 500, 100, 50, 20, 10, 5, 2, 1):
        count, whole_baht = divmod(whole_baht, value)
        if count:
            denominations.append({
                "value": value,
                "count": count,
                "kind": "ธนบัตร" if value >= 20 else "เหรียญ",
            })
    if remaining_satang:
        denominations.append({"value": remaining_satang / 100, "count": 1, "kind": "เศษสตางค์"})
    return denominations
