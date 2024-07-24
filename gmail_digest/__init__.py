import base64
import datetime
import logging
import os
import pickle
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from string import Template

import click
import markdown
from decouple import config
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
    # "https://www.googleapis.com/auth/gmail.metadata",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.modify",
]

DIGEST_DESTINATION = config("DIGEST_DESTINATION", cast=str)


@click.command()
@click.option("--dry-run", is_flag=True, default=False, help="Run script without creating sending")
def main(dry_run):
    logging.basicConfig(level=logging.INFO)
    generate_digest_email(dry_run)


def generate_digest_email(dry_run):
    pass


# TODO this should really be much smarter
def _extract_credentials():
    creds = None

    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return creds


def send_digest(markdown_content, dry_run=False):
    creds = _extract_credentials()
    service = build("gmail", "v1", credentials=creds)

    message = MIMEMultipart("alternative")
    message["to"] = DIGEST_DESTINATION
    message["subject"] = f"Email Digest for {datetime.datetime.now().strftime('%Y-%m-%d')}"
    content = markdown.markdown(markdown_content)
    message.attach(MIMEText(content, "html"))

    raw_message = base64.urlsafe_b64encode(message.as_bytes())
    raw_message = raw_message.decode()
    body = {"raw": raw_message}

    if not dry_run:
        sent_message = service.users().messages().send(userId="me", body=body).execute()

    logging.info(f"digest email sent")
