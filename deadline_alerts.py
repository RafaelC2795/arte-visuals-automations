#!/usr/bin/env python3
"""
deadline_alerts.py — Alertas de deadline do Notion por email
Corre diariamente via cron. Envia email 30, 15 e 3 dias antes do Deadline.
"""

import os
import sys
import json
import base64
from pathlib import Path
from datetime import date, datetime

# ==============================================================================
PROJETOS_DB     = "627d6147-63b0-83f2-8677-01ec7f0ac715"
EMAIL_DESTINO   = "hello@itsartevisuals.com"
DIAS_ALERTA     = [30, 15, 3]
ENV_PATH        = Path("/Users/rc/CLAUDE CODE/Arte Visuals/.env")
TOKEN_PATH      = Path.home() / ".claude" / "gmail_token_send.json"
# ==============================================================================

def install_deps():
    import subprocess
    packages = [
        "notion-client", "google-api-python-client",
        "google-auth-oauthlib", "google-auth-httplib2"
    ]
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q"] + packages)

try:
    from notion_client import Client
    from googleapiclient.discovery import build
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
except ImportError:
    install_deps()
    from notion_client import Client
    from googleapiclient.discovery import build
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def load_env():
    # No GitHub Actions as variáveis vêm dos Secrets (já estão no ambiente)
    # Localmente lê do ficheiro .env se existir
    if ENV_PATH.exists():
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


def get_gmail_credentials():
    client_id     = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_info(
            json.loads(TOKEN_PATH.read_text()), SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            config = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uris": ["http://localhost"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
            flow = InstalledAppFlow.from_client_config(config, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())

    return creds


def send_email(service, destinatario: str, assunto: str, corpo: str):
    from email.mime.text import MIMEText
    msg = MIMEText(corpo, "html", "utf-8")
    msg["To"]      = destinatario
    msg["From"]    = destinatario
    msg["Subject"] = assunto
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


def get_projetos(notion: Client) -> list:
    results, cursor = [], None
    while True:
        kwargs = {"database_id": PROJETOS_DB}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.databases.query(**kwargs)
        results.extend(resp["results"])
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return results


def main():
    load_env()
    notion_token = os.environ.get("NOTION_TOKEN", "")
    if not notion_token:
        print("ERRO: NOTION_TOKEN não encontrado")
        sys.exit(1)
    notion  = Client(auth=notion_token)
    creds   = get_gmail_credentials()
    gmail   = build("gmail", "v1", credentials=creds)
    hoje    = date.today()
    projetos = get_projetos(notion)

    alertas_enviados = 0

    for p in projetos:
        props    = p["properties"]
        deadline = props.get("Deadline", {}).get("date")
        if not deadline or not deadline.get("start"):
            continue

        deadline_date = datetime.strptime(deadline["start"], "%Y-%m-%d").date()
        dias_restantes = (deadline_date - hoje).days

        if dias_restantes not in DIAS_ALERTA:
            continue

        # Nome do projeto
        titulo_prop = props.get("Projeto", {}).get("title", [])
        nome = titulo_prop[0].get("plain_text", "Projeto sem nome") if titulo_prop else "Projeto sem nome"

        # Estado
        estado = props.get("Estado do Projeto", {}).get("select", {})
        estado_nome = estado.get("name", "—") if estado else "—"

        # Responsável
        responsavel_prop = props.get("Responsável interno", {}).get("people", [])
        responsavel = responsavel_prop[0].get("name", "—") if responsavel_prop else "—"

        assunto = f"⏰ Alerta: '{nome}' — faltam {dias_restantes} dias para o deadline"

        corpo = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #e74c3c;">⏰ Alerta de Deadline</h2>
            <p>Faltam <strong>{dias_restantes} dias</strong> para o deadline do seguinte projeto:</p>
            <table style="width:100%; border-collapse:collapse; margin-top:16px;">
                <tr style="background:#f8f8f8;">
                    <td style="padding:10px; font-weight:bold; border:1px solid #ddd; width:40%">Projeto</td>
                    <td style="padding:10px; border:1px solid #ddd;">{nome}</td>
                </tr>
                <tr>
                    <td style="padding:10px; font-weight:bold; border:1px solid #ddd;">Deadline</td>
                    <td style="padding:10px; border:1px solid #ddd;">{deadline_date.strftime("%d/%m/%Y")}</td>
                </tr>
                <tr style="background:#f8f8f8;">
                    <td style="padding:10px; font-weight:bold; border:1px solid #ddd;">Estado</td>
                    <td style="padding:10px; border:1px solid #ddd;">{estado_nome}</td>
                </tr>
                <tr>
                    <td style="padding:10px; font-weight:bold; border:1px solid #ddd;">Responsável</td>
                    <td style="padding:10px; border:1px solid #ddd;">{responsavel}</td>
                </tr>
            </table>
            <p style="margin-top:24px; color:#888; font-size:12px;">Arte Visuals — Alerta automático</p>
        </div>
        """

        send_email(gmail, EMAIL_DESTINO, assunto, corpo)
        print(f"✓ Email enviado: '{nome}' — {dias_restantes} dias")
        alertas_enviados += 1

    if alertas_enviados == 0:
        print(f"{hoje} — Sem alertas para hoje.")
    else:
        print(f"{hoje} — {alertas_enviados} alerta(s) enviado(s).")


if __name__ == "__main__":
    main()
