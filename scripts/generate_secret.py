"""Print a random 64-character secret suitable for APP_SECRET_KEY / ADMIN_TOKEN."""
import secrets

print(secrets.token_urlsafe(48))
