"""Create a private Docker Compose .env interactively, without echoing credentials."""
import getpass
import os
from pathlib import Path
import secrets


def env_value(value):
    if any(char in value for char in ("\n", "\r", "\x00")):
        raise ValueError("Configuration values must be a single line.")
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def main():
    root = Path(__file__).resolve().parents[1]
    target = root / ".env"
    if target.exists():
        raise SystemExit(".env already exists; edit it directly. Nothing was overwritten.")
    password = getpass.getpass("Site access password (at least 12 characters): ")
    if len(password) < 12:
        raise SystemExit("Choose a password with at least 12 characters.")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    domain = input("Domain for HTTPS (blank for local / SSH tunnel): ").strip()
    base_url = input("AI base URL (blank for offline only): ").strip().rstrip("/")
    model = input("AI model (blank for offline only): ").strip() if base_url else ""
    key = getpass.getpass("AI API key: ") if base_url else ""
    values = {
        "TEACHBUDDY_PASSWORD": password,
        "TEACHBUDDY_SECRET": secrets.token_urlsafe(48),
        "TEACHBUDDY_DOMAIN": domain,
        "TEACHBUDDY_PORT": "8765",
        "TEACHBUDDY_SECURE_COOKIE": "true" if domain else "false",
        "AI_BASE_URL": base_url,
        "AI_MODEL": model,
        "AI_API_KEY": key,
        "AI_TIMEOUT": "90",
    }
    content = "\n".join(name + "=" + env_value(value) for name, value in values.items()) + "\n"
    descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    print("Created private .env. Credentials were not printed. Do not commit this file.")


if __name__ == "__main__":
    main()