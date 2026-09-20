"""Email body cleanup and sender identity normalization.

Quoted reply chains double- and triple-count old text on every reply in a thread; if left
in, they dominate both word/question counts and topic clustering. This strips them before
anything gets stored.
"""
from __future__ import annotations

import re
from email.utils import parseaddr

from email_reply_parser import EmailReplyParser

_SIGNATURE_MARKERS = re.compile(
    r"^\s*(--\s*$|__+|Best,|Regards,|Thanks,|Cheers,|Sent from my )",
    re.IGNORECASE | re.MULTILINE,
)


def clean_body(raw_text: str) -> str:
    """Strip quoted reply chains and trailing signatures from a message body."""
    if not raw_text:
        return ""
    reply_only = EmailReplyParser.parse_reply(raw_text)
    match = _SIGNATURE_MARKERS.search(reply_only)
    if match:
        reply_only = reply_only[: match.start()]
    return reply_only.strip()


def normalize_sender(header_value: str) -> tuple[str, str]:
    """Return (email, display_name) from a raw From/To/Cc address, lowercased for grouping."""
    name, email = parseaddr(header_value or "")
    return email.strip().lower(), name.strip()
