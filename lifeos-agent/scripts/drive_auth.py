"""
Разовая авторизация Google Drive (Фаза 2 Media Inbox, см.
specs/010-media-inbox.md). Запускается ЛОКАЛЬНО (не в Docker) — открывает
браузер для согласия, сохраняет refresh-токен в token.json. Дальше бот
(в контейнере) обновляет access-токен по refresh_token сам, без браузера.

Использование:
    python scripts/drive_auth.py

Требует credentials.json рядом (см. .gitignore — оба файла в него уже
добавлены, не коммитятся).

Scope — drive.file (не полный drive): бот видит и может создавать только
файлы/папки, которые сам же создал, а не весь Диск целиком. Минимально
достаточное право (принцип "Надёжность" из PROJECT.md).
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    print(f"Готово: {TOKEN_FILE} сохранён.")


if __name__ == "__main__":
    main()
