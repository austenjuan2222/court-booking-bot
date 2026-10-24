from datetime import datetime, timedelta, timezone

TAIPEI = timezone(timedelta(hours=8))


def next_saturday(now=None):
    today = (now or datetime.now(TAIPEI)).astimezone(TAIPEI).date()
    return today + timedelta(days=(5 - today.weekday()) % 7 or 7)


def choose_plan(rows, hours=(15, 16), max_total=900):
    available = {}
    for hour in hours:
        available[hour] = {row['court']: row for row in rows
                           if row['hour'] == hour and row['available']
                           and isinstance(row['price'], (int, float)) and row['price'] > 0}
    if any(not available[hour] for hour in hours):
        return None
    common = set.intersection(*(set(available[hour]) for hour in hours))
    candidates = []
    for court in sorted(common):
        candidates.append([available[hour][court] for hour in hours])
    # A complete same-court plan always takes priority over split-court plans.
    import itertools
    candidates.extend(list(plan) for plan in itertools.product(*(available[h].values() for h in hours)))
    for plan in candidates:
        if sum(row['price'] for row in plan) <= max_total:
            return plan
    return None
