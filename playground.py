#!/usr/bin/env -S ipython -i

import base64
import datetime
import email
import re

import funcy as f
import funcy_pipe as fp
from googleapiclient.discovery import build

from gmail_digest import _extract_credentials

DIGEST_DAYS = 1

def get_header(message, header):
    header = message['payload']['headers'] | fp.where(name=header) | fp.first()
    return header['value']

def get_full_message(service, message_id):
    # Fetch the full message using the Gmail API
    message = service.users().messages().get(userId='me', id=message_id, format='full').execute()

    parts = message['payload']['parts']

    # if len(parts) > 1:
    #     print("lots of parts")

    plain_text, html_text = extract_html_and_plain_text(parts)
    mime_msg = email.message_from_string(html_text)

    if not plain_text:
        plain_text = mime_msg.get_payload()
        breakpoint()

    from_email = get_header(message, "From")
    to_email = get_header(message, "To")
    subject = get_header(message, "Subject")

    return {
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
        plain_part = multipart['parts'] | fp.where(mimeType="text/plain") | fp.first()
        html_part = multipart['parts'] | fp.where(mimeType="text/html") | fp.first()

    plain_text = None
    if plain_part:
        plain_text = base64.urlsafe_b64decode(f.get_in(plain_part, ["body", "data"]).encode('ASCII')).decode('utf-8')

    html_text = None
    if html_part:
      html_text = base64.urlsafe_b64decode(f.get_in(html_part, ["body", "data"]).encode('ASCII')).decode('utf-8')

    return plain_text, html_text

def get_sent_messages(service):
    now = datetime.datetime.utcnow()
    yesterday = now - datetime.timedelta(days=DIGEST_DAYS)
    query = f'after:{int(yesterday.timestamp())} before:{int(now.timestamp())}'

    results = service.users().messages().list(userId='me', q=query, labelIds=['SENT']).execute()
    messages = results.get('messages', [])
    return messages

def format_message(message):
    return f"""
# {message['subject']}

**From:** {message['from']}
**To:** {message['to']}

---

{message['truncated_plain_text']}

    """

def truncate_long_threads(message):
    """
    Only include the last two messages from a thread.

    In plain text, threads are structured like:

    > On Thu, Jun 13 , 2024 at 3:06 PM, Scott King < SEKing@ franciscan. edu (
    > SEKing@franciscan.edu ) > wrote:
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
    # thread_pattern = re.compile(r"^>{2,}\s")
    truncated_plain_text = plain_text_message.split("\n") | fp.remove("^>{2,}\s") | fp.join_str("\n")

    message['truncated_plain_text'] = truncated_plain_text
    return message

creds = _extract_credentials()
service = build("gmail", "v1", credentials=creds)
messages = get_sent_messages(service)
transformed_messages = messages | fp.pluck("id") | fp.map(fp.partial(get_full_message, service)) | fp.map(truncate_long_threads) | fp.to_list()
formatted_markdown = transformed_messages | fp.map(format_message) | fp.join_str("\n")

prompt_and_messages = f"""
Below are messages sent from my email account over the last day. I would like a concise summary of my activity over the last day. I am not the
only one operating in my inbox.

for each message add a bullet indicating who the message is to and a one-sentence summary of what was said.

Exclude:

* unsubscribe requests
* forwarded verification code emails
* messages sent to todoist

Here's an example bullet:

* **John Doe.** Asked when he would be available to meet.
* **Jane Doe.** Reminded her of previous unanswered email.

Below are the messages:

{formatted_markdown}
"""

from openai import OpenAI


def ai_summary(text):
    client = OpenAI(
      # This is the default and can be omitted
      # api_key=os.environ.get("OPENAI_API_KEY"),
    )

    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": text,
            }
        ],
        model="gpt-4o",
    )

    return chat_completion.choices[0].message.content

summary = ai_summary(prompt_and_messages)
print(summary)