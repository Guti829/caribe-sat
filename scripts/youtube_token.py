"""Ejecuta UNA vez en tu computador para obtener el refresh token de YouTube.

1. En Google Cloud Console: habilita "YouTube Data API v3" y crea un
   cliente OAuth de tipo "App de escritorio". Descarga client_secret.json aquí.
2. python scripts/youtube_token.py
3. Copia los tres valores impresos a tus secretos (YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN).
"""
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json", scopes=["https://www.googleapis.com/auth/youtube.upload"])
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
print("YT_CLIENT_ID=", creds.client_id)
print("YT_CLIENT_SECRET=", creds.client_secret)
print("YT_REFRESH_TOKEN=", creds.refresh_token)
