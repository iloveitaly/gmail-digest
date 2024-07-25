#!/usr/bin/env -S ipython -i

from gmail_digest import *

service = build_gmail_service()


def get_gmail_message(service, message_id):
    return service.users().messages().get(userId="me", id=message_id).execute()


print(
    """
get_full_message(service, "190e9d7e51d6425c")
"""
)
