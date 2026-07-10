from decimal import Decimal


def format_cents(value: int | None, currency: str = "USD") -> str:
    if value is None:
        return "$0.00"

    amount = Decimal(value) / Decimal(100)

    if currency == "USD":
        return f"${amount:,.2f}"

    return f"{amount:,.2f} {currency}"