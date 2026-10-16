import io
import json
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaInMemoryUpload

load_dotenv()

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

SCOPES = ["https://www.googleapis.com/auth/drive"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def save_token_with_timestamps(creds: Credentials, output_path: str):
    """Saves only token values and timestamps to JSON,

    excluding client_id and client_secret.
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
        "oauth_credentials": {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri or "https://oauth2.googleapis.com/token",
            "scopes": creds.scopes,
        },
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=4)

    print(f"[+] Token updated without client credentials at: {output_path}")


def get_drive_service():
    """Builds the Google Drive service by combining token.json

    with CLIENT_ID and CLIENT_SECRET from .env.
    """
    creds = None

    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                oauth_info = data.get("oauth_credentials", data).copy()

                # Inject credentials from .env
                oauth_info["client_id"] = CLIENT_ID
                oauth_info["client_secret"] = CLIENT_SECRET

                creds = Credentials.from_authorized_user_info(oauth_info, SCOPES)
        except Exception as e:
            print(f"[!] Warning reading token: {e}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_token_with_timestamps(creds, TOKEN_FILE)
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Missing '{CREDENTIALS_FILE}'. Download it from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            save_token_with_timestamps(creds, TOKEN_FILE)

    return build("drive", "v3", credentials=creds)


def get_file(file_id: str = "", file_name: str = "") -> dict:
    """Retrieve metadata and timestamps for a single file by its ID or Name."""
    service = get_drive_service()

    if file_id:
        return service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size, createdTime, modifiedTime, trashed, parents"
        ).execute()

    if file_name:
        query = f"name = '{file_name}' and trashed = false"
        results = service.files().list(
            q=query,
            pageSize=1,
            fields="files(id, name, mimeType, size, createdTime, modifiedTime, trashed, parents)"
        ).execute()
        files = results.get("files", [])
        if not files:
            return {"error": f"File '{file_name}' not found."}
        return files[0]

    return {"error": "Provide either file_id or file_name."}


def get_many_files(page_size: int = 10, search_query: str = "", folder_id: str = "") -> list[dict]:
    """List or search multiple files ordered by last modified timestamp."""
    service = get_drive_service()

    q_parts = ["trashed = false"]
    if search_query:
        q_parts.append(f"name contains '{search_query}'")
    if folder_id:
        q_parts.append(f"'{folder_id}' in parents")

    results = service.files().list(
        q=" and ".join(q_parts),
        pageSize=min(page_size, 50),
        orderBy="modifiedTime desc",
        fields="files(id, name, mimeType, size, createdTime, modifiedTime)"
    ).execute()

    return results.get("files", [])

def get_file_content(file_id: str) -> dict:
    """Download or export the textual content of a file along with its metadata."""
    service = get_drive_service()

    metadata = service.files().get(
        fileId=file_id,
        fields="id, name, mimeType, createdTime, modifiedTime"
    ).execute()

    mime_type = metadata.get("mimeType", "")

    if mime_type == "application/vnd.google-apps.document":
        request = service.files().export_media(fileId=file_id, mimeType="text/plain")
    elif mime_type == "application/vnd.google-apps.spreadsheet":
        request = service.files().export_media(fileId=file_id, mimeType="text/csv")
    else:
        request = service.files().get_media(fileId=file_id)

    stream = io.BytesIO()
    downloader = MediaIoBaseDownload(stream, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    content = stream.getvalue().decode("utf-8", errors="replace")

    return {
        "file_id": file_id,
        "name": metadata.get("name"),
        "mime_type": mime_type,
        "created_at": metadata.get("createdTime"),
        "last_modified": metadata.get("modifiedTime"),
        "content": content
    }


def delete_files(file_ids: list[str], permanent: bool = False) -> dict:
    """Delete one or multiple files by ID (defaults to moving to trash)."""
    service = get_drive_service()
    success, failed = [], []

    for fid in file_ids:
        try:
            if permanent:
                service.files().delete(fileId=fid).execute()
            else:
                service.files().update(fileId=fid, body={"trashed": True}).execute()
            success.append(fid)
        except Exception as e:
            failed.append({"file_id": fid, "error": str(e)})

    return {
        "status": "completed",
        "action": "permanent_delete" if permanent else "move_to_trash",
        "deleted_count": len(success),
        "deleted_file_ids": success,
        "failed": failed
    }

def create_files(name: str, content: str, mime_type: str = "text/plain", folder_id: str = "") -> dict:
    """Create a new file with content in Google Drive."""
    service = get_drive_service()

    file_metadata = {"name": name}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaInMemoryUpload(
        content.encode("utf-8"),
        mimetype=mime_type,
        resumable=False
    )

    created_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, mimeType, createdTime, modifiedTime"
    ).execute()

    return {
        "status": "success",
        "created_file": created_file
    }

if __name__ == "__main__":
    print("Testing tools.py...")
    files = get_many_files(page_size=3)
    print(f"Retrieved {len(files)} files successfully.")
    for f in files:
        print(f" - {f.get('name')} (ID: {f.get('id')}) | Modified: {f.get('modifiedTime')}")