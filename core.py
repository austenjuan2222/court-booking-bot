"""Booking planning and email primitives. Used by local booking workflow."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import smtplib
import ssl

TAIPEI = timezone(timedelta(hours=8))


def next_release(now=None):
    """Next Saturday midnight, strictly after now, in Taiwan time."""
    now = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    candidate = now.replace(hour=0, minute=0, second=0, microsecond=0)
    candidate += timedelta(days=(5 - now.weekday()) % 7)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def target_date(release):
    local = release.astimezone(TAIPEI)
    if local.weekday() != 5 or (local.hour, local.minute, local.second) != (0, 0, 0):
        raise ValueError("Release must be Saturday 00:00 in Taiwan time")
    return (local + timedelta(days=7)).date()


def choose_courts(available, slots, allow_different=True):
    """available maps exact slot labels to court IDs; returns a complete plan only."""
    if not slots or len(set(slots)) != len(slots):
        raise ValueError("Slots must be nonempty and unique")
    choices = [set(available.get(slot, [])) for slot in slots]
    if any(not choice for choice in choices):
        return None
    common = set.intersection(*choices)
    if common:
        court = sorted(common)[0]
        return dict.fromkeys(slots, court)
    if allow_different:
        return {slot: sorted(choice)[0] for slot, choice in zip(slots, choices)}
    return None


def send_notice(host, port, username, password, recipient, subject, body):
    """Send through authenticated SMTP with STARTTLS; secrets supplied at runtime."""
    message = EmailMessage()
    message['From'] = username
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(body)
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(username, password)
        refused = smtp.send_message(message)
        if refused:
            raise RuntimeError("SMTP rejected recipient")
