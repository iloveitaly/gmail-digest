import base64
import datetime
import email
import logging
import pickle
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import click
import funcy as f
import funcy_pipe as fp
import markdown
from decouple import config
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from openai import OpenAI

from .util import log, root

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
    # "https://www.googleapis.com/auth/gmail.metadata",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.modify",
]

DIGEST_DESTINATION = config("DIGEST_DESTINATION", cast=str)
DIGEST_DAYS = config("DIGEST_DAYS", cast=int, default=1)
SUPERHUMAN_LINK = config("SUPERHUMAN_LINK", cast=bool, default=True)

TOKEN_PATH = root / "data/token.pickle"
CREDENTIALS_PATH = root / "data/credentials.json"

OPENAI_MODEL = "gpt-4o"


@click.command()
@click.option("--dry-run", is_flag=True, default=False, help="Run script without sending an email")
def main(dry_run):
    logging.basicConfig(level=logging.INFO)
    generate_digest_email(dry_run)


def generate_digest_email(dry_run):
    creds = _extract_credentials()
    service = build("gmail", "v1", credentials=creds)

    messages = get_sent_messages(service)

    transformed_messages = (
        messages
        | fp.pluck("id")
        | fp.map(fp.partial(get_full_message, service))
        | fp.map(truncate_long_threads)
        | fp.to_list()
    )

    formatted_markdown = transformed_messages | fp.map(format_message) | fp.join_str("\n")

    prompt_and_messages = f"""
Below are messages sent from my email account over the last day. I would like a concise summary of my activity over the last day. I am not the
only one operating in my inbox.

For each message, write a bullet indicating who the message is to and a one-sentence summary of what was said. If an assistant sent the message, include context about who the assistant is working for.

Exclude:

* unsubscribe requests
* forwarded verification code emails
* messages sent to todoist

If after excluding these messages, there are no messages left, return an empty string.

Here are some example summaries to use as a template:

* 190e654d26e12dcd **John Doe.** Asked when he would be available to meet.
* 190ea77b5760880c **Jane Doe.** Reminded her of previous unanswered email.

These alphanumeric IDs are 'Message IDs' included right after the subject of the email. These are unique to each message.

Below are the messages:

{formatted_markdown}
"""
    summary = ai_summary(prompt_and_messages)

    if not summary:
        log.info("no messages to summarize")
        return

    summary_with_gmail_links = add_gmail_links(service, summary)
    send_digest(summary_with_gmail_links)

    log.debug("summary content", content=summary_with_gmail_links)


def _extract_credentials():
    creds = None

    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "wb") as token:
            pickle.dump(creds, token)

    return creds


def get_authenticated_email(service):
    user_profile = service.users().getProfile(userId="me").execute()
    return user_profile["emailAddress"]


def build_gmail_service():
    creds = _extract_credentials()
    return build("gmail", "v1", credentials=creds)


def send_digest(markdown_content, dry_run=False):
    service = build_gmail_service()
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


def get_header(message, header_name):
    # normalize to uppercase headers
    headers = message["payload"]["headers"]
    header = headers | fp.filter(lambda h: h["name"].upper() == header_name.upper()) | fp.first()

    if not header:
        log.warn("header not found", header=header_name)

    return header["value"]


def add_gmail_links(service, summary: str):
    """
    Assumes summary contains format `* 190e654d26e12dcd **John Doe.** ...`

    This will hyperlink the name to the Gmail message.
    """

    account_email = get_authenticated_email(service)

    if SUPERHUMAN_LINK:
        link_generator = fp.partial(generate_superhuman_link, account_email)
    else:
        link_generator = generate_gmail_link

    def replace_match(match):
        return f"* [{match.group(2)}]({link_generator(match.group(1))})"

    lines = summary.splitlines()
    processed_lines = [re.sub(r"\*\s([0-9a-z]+)\s\*\*([^*]+)\*\*", replace_match, line) for line in lines]
    return "\n".join(processed_lines)


def generate_gmail_link(message_id: str) -> str:
    return f"https://mail.google.com/mail/u/0/#inbox/{message_id}"


def generate_superhuman_link(account_email: str, message_id: str) -> str:
    "Similar to gmail format: https://mail.superhuman.com/email@address.com/thread/190e9d7e51d6425c#app"

    return f"https://mail.superhuman.com/{account_email}/thread/{message_id}#app"


def get_full_message(service, message_id):
    # Fetch the full message using the Gmail API
    message = service.users().messages().get(userId="me", id=message_id, format="full").execute()

    parts = message["payload"]["parts"]

    # if len(parts) > 1:
    #     print("lots of parts")

    plain_text, html_text = extract_html_and_plain_text(parts)
    mime_msg = email.message_from_string(html_text)

    if not plain_text:
        plain_text = mime_msg.get_payload()

    from_email = get_header(message, "From")
    to_email = get_header(message, "To")
    subject = get_header(message, "Subject")

    return {
        "id": message_id,
        "thread_id": message["threadId"],
        "from": from_email,
        "to": to_email,
        "subject": subject,
        "plain_text": plain_text,
        # TODO not sure if this is the best approach
        "html_text": mime_msg.as_string(),
    }


def extract_html_and_plain_text(parts):
    plain_text = None
    html_text = None

    plain_part = parts | fp.where(mimeType="text/plain") | fp.first()
    html_part = parts | fp.where(mimeType="text/html") | fp.first()

    # probably a multipart message
    if not plain_part and not html_part:
        multipart = parts | fp.where(mimeType="multipart/alternative") | fp.first()
        plain_part = multipart["parts"] | fp.where(mimeType="text/plain") | fp.first()
        html_part = multipart["parts"] | fp.where(mimeType="text/html") | fp.first()

    plain_text = None
    if plain_part:
        plain_text = base64.urlsafe_b64decode(f.get_in(plain_part, ["body", "data"]).encode("ASCII")).decode("utf-8")

    html_text = None
    if html_part:
        html_text = base64.urlsafe_b64decode(f.get_in(html_part, ["body", "data"]).encode("ASCII")).decode("utf-8")

    return plain_text, html_text


def get_sent_messages(service):
    now = datetime.datetime.now()
    yesterday = now - datetime.timedelta(days=DIGEST_DAYS)
    query = f"after:{int(yesterday.timestamp())} before:{int(now.timestamp())} -subject:(Email Digest for)"

    log.info("searching for messages", query=query)

    results = service.users().messages().list(userId="me", q=query, labelIds=["SENT"]).execute()
    messages = results.get("messages", [])

    log.info("messages found", count=len(messages))
    return messages


def format_message(message):
    return f"""
# [message]: {message['subject']}

**Message ID:** {message['thread_id']}
**From:** {message['from']}
**To:** {message['to']}

---

{message['truncated_plain_text']}

    """


def truncate_long_threads(message):
    """
    Only include the last two messages from a thread.

    In plain text, threads are structured like:

    > On Thu, Jun 13 , 2024 at 3:06 PM, Scott Prince < SEKing@ school. edu (
    > SEKing@school.edu ) > wrote:
    >
    >> Hi Mike,
    >>
    >>
    >> Thanks for getting back to me.  Just reach back out when your back in town
    >> and enjoy the family trip.
    >>

    Any line that starts with two or more `>` followed by a space should be removed
    """

    plain_text_message = message["plain_text"]
    truncated_plain_text = plain_text_message.split("\n") | fp.remove("^>{2,}\s") | fp.join_str("\n")

    message["truncated_plain_text"] = truncated_plain_text
    return message


def ai_summary(prompt):
    client = OpenAI()
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model=OPENAI_MODEL,
    )

    return chat_completion.choices[0].message.content
