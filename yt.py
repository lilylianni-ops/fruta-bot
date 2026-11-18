from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from store import ROOT

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def service():
    tok, creds = ROOT / "token.json", None
    if tok.exists():
        creds = Credentials.from_authorized_user_file(str(tok), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(str(ROOT / "client_secret.json"), SCOPES).run_local_server(port=0)
        tok.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload(path, e, privacy):
    title = (e["title"] + " #Shorts")[:100]
    desc = f"{e['description']}\n\nContenido creado con ayuda de IA.\n#Shorts #FrutasNovelas"
    body = {
        "snippet": {"title": title, "description": desc, "tags": e.get("tags", []), "categoryId": "24"},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True},
    }
    req = service().videos().insert(part="snippet,status", body=body,
                                    media_body=MediaFileUpload(str(path), chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]
