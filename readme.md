# Gmail Digest

## Installation

```shell
pip install -U gmail-digest
```

## Usage

```shell
Usage: gmail-digest [OPTIONS]

Options:
  --dry-run  Run script without creating sending
  --help     Show this message and exit.
```

### Extra filter

You can customize the gmail query used to collect emails to summarize:

```shell
GMAIL_FILTER_SUFFIX='-to:personal@gmail.com -to:readwise.io -to:todoist.com'
```

## Development

Test the tool by running it locally and increasing `DIGEST_DAYS`.

Need to debug OpenAI/prompt issues? [Enable debug logging.](https://stackoverflow.com/questions/76256249/logging-in-the-open-ai-python-library/78214464#78214464)

## Setup

You need to create a "OAuth 2.0 Client IDs" which has to be done with a Google Workspace (gsuite). This will not work on a personal gmail account (unless you create a app on a workspace and add your personal account as a test account).

### Generating a Gmail API Token

1. Navigate to the Google Cloud Console. https://console.developers.google.com/
2. Create a new project or select an existing one.
3. Go to "APIs & Services" -> "Library" and enable the Gmail API.
4. Navigate to "APIs & Services" -> "Credentials".
5. Click "Create Credentials" -> "OAuth client ID".
6. Select "Desktop app" as the application type, then click "Create".
7. Download the JSON file, rename it to `credentials.json`, and place it in the root of this project.
8. Run the script and oauth into your account

If you want to edit scopes on an existing application, you can:

1. OAuth Consent Screen
2. Edit
3. Continue to step 2
4. Add or remove scopes
5. Add scopes and save

#### Credential Scopes Needed

Two main scopes are required for this:

* `https://www.googleapis.com/auth/gmail.compose`
* `https://www.googleapis.com/auth/gmail.readonly`

Some other scopes I'd add so you can reuse the credentials in other projects, [like gmailctl](https://github.com/mbrt/gmailctl) or calendar scripts:

* `https://www.googleapis.com/auth/calendar.readonly`
* `https://www.googleapis.com/auth/calendar.event`
* `https://www.googleapis.com/auth/gmail.labels`
* `https://www.googleapis.com/auth/gmail.settings.basic`
