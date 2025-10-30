from datetime import datetime, date, timedelta


def market_today(reference: datetime | None = None) -> date:
    """Return the 'market' date to use for daily data requests.

    Rules (matching existing JQuants logic used elsewhere):
    - If current time is before 15:30, treat today as previous calendar day (use previous trading day)
    - If resultant day is Saturday or Sunday, roll back to Friday

    The function accepts an optional reference datetime for testing.
    """
    now = reference or datetime.now()
    today = date.today()
    # If before market close (15:30), use previous calendar day
    if (now.hour < 15) or (now.hour == 15 and now.minute < 30):
        today = today - timedelta(days=1)

    # Adjust weekends: if Saturday -> Friday; if Sunday -> Friday
    if today.weekday() == 5:  # Saturday
        today = today - timedelta(days=1)
    elif today.weekday() == 6:  # Sunday
        today = today - timedelta(days=2)

    return today
