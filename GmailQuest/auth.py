"""Gmail OAuth: one-time user consent in a browser, cached refresh token after that.

Requires a Google Cloud project with the Gmail API enabled and an OAuth client (type
"Desktop app") whose client-secret JSON is saved to CREDENTIALS_PATH. See README.md.
"""
from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from GmailQuest.config import CREDENTIALS_PATH, GMAIL_SCOPES, TOKEN_PATH


def _load_credentials() -> Credentials:
    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), GMAIL_SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(
                f"No OAuth client secret found at {CREDENTIALS_PATH}. Download it from Google "
                "Cloud Console (OAuth client, type 'Desktop app') and save it there — see "
                "README.md for the full setup steps."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), GMAIL_SCOPES)
        creds = flow.run_local_server(port=0)

    TOKEN_PATH.write_text(creds.to_json())
    return creds


def get_gmail_service() -> Resource:
    creds = _load_credentials()
    return build("gmail", "v1", credentials=creds)
