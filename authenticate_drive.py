import json
import os
from datetime import datetime, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Drive read-only scope
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def save_token_with_timestamps(creds: Credentials, output_path: str):
    """Saves OAuth credentials to a JSON file along with creation,

    last refreshed, and expiration timestamps in ISO 8601 format.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    expiry_iso = (
        creds.expiry.replace(tzinfo=timezone.utc).isoformat()
        if creds.expiry
        else None
    )

    token_data = {
        "timestamps": {
            "created_at": now_iso,
            "last_refreshed_at": now_iso,
            "expires_at": expiry_iso,
        },
        # OAuth 2.0 Credentials payload
        "oauth_credentials": {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
        },
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=4)

    print(f"\n[+] Token saved with timestamps to: {output_path}")


def authenticate_google_drive():
    """Performs OAuth 2.0 authorization code flow or refreshes an existing token."""
    creds = None

    # 1. Check if token file already exists
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                oauth_info = data.get("oauth_credentials", data)
                creds = Credentials.from_authorized_user_info(
                    oauth_info, SCOPES
                )
        except Exception as e:
            print(f"[!] Warning reading existing token: {e}")
            creds = None

    # 2. If token is missing or invalid, refresh or trigger consent flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[*] Access token expired. Refreshing token...")
            creds.refresh(Request())
            save_token_with_timestamps(creds, TOKEN_FILE)
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"'{CREDENTIALS_FILE}' not found. Place your downloaded client secret JSON in this folder."
                )

            print(
                "[*] Launching local browser for Google OAuth consent screen..."
            )
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)
            save_token_with_timestamps(creds, TOKEN_FILE)

    print("[✔] OAuth 2.0 authentication completed successfully!")
    return creds


if __name__ == "__main__":
    authenticate_google_drive()