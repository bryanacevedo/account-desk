"""Settings read from the environment once. Nothing secret is ever logged or stored in the database."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    # A mailbox that really receives mail and forwards it to the reply webhook; without one, only the https
    # one-click link is offered (RFC 8058 needs only that).
    unsubscribe_mailto: str = field(default_factory=lambda: os.environ.get("UNSUBSCRIBE_MAILTO", ""))
    database_url: str = field(default_factory=lambda: os.environ.get(
        "DATABASE_URL", "postgres://postgres@127.0.0.1:54329/outbound"))
    mode: str = field(default_factory=lambda: os.environ.get("MODE", "demo"))  # demo | live
    public_demo: bool = field(default_factory=lambda: _flag("PUBLIC_DEMO"))
    live_send: bool = field(default_factory=lambda: _flag("LIVE_SEND"))
    auth_mode: str = field(default_factory=lambda: os.environ.get("AUTH_MODE", "demo"))  # demo | header
    auth_header: str = field(default_factory=lambda: os.environ.get("AUTH_HEADER", "Cf-Access-Authenticated-User-Email"))
    write_key: str = field(default_factory=lambda: os.environ.get("WRITE_KEY", ""))
    # Unset means a random secret for this process only: fine for a demo that resets, refused in live mode.
    webhook_secret: str = field(default_factory=lambda: os.environ.get("WEBHOOK_SECRET") or secrets.token_hex(32))
    webhook_secret_set: bool = field(default_factory=lambda: bool(os.environ.get("WEBHOOK_SECRET")))
    # A LinkedIn tool (HeyReach) cannot sign its webhooks, so it calls a URL with this token in it. Unset: off.
    linkedin_tool_token: str = field(default_factory=lambda: os.environ.get("LINKEDIN_TOOL_TOKEN", ""))
    access_team_domain: str = field(default_factory=lambda: os.environ.get("CF_ACCESS_TEAM_DOMAIN", ""))
    access_aud: str = field(default_factory=lambda: os.environ.get("CF_ACCESS_AUD", ""))
    public_url: str = field(default_factory=lambda: os.environ.get("PUBLIC_URL", "http://localhost:8800"))
    sender_company: str = field(default_factory=lambda: os.environ.get("SENDER_COMPANY", "Lumen Ledger"))
    sender_address: str = field(default_factory=lambda: os.environ.get(
        "SENDER_ADDRESS", "Lumen Ledger, 400 Market Street, Suite 210, Philadelphia, PA 19106, USA"))
    privacy_url: str = field(default_factory=lambda: os.environ.get("PRIVACY_URL", "https://lumenledger.example/privacy"))
    anthropic_live: bool = field(default_factory=lambda: _flag("ANTHROPIC_LIVE"))
    evals_strict: bool = field(default_factory=lambda: _flag("EVALS_STRICT"))
    slack_token: str = field(default_factory=lambda: os.environ.get("SLACK_BOT_TOKEN", ""))
    # Google Postmaster Tools API v2: an OAuth client and a refresh token from the Google account that verified the
    # sending domains in Postmaster Tools. Any of the three unset: no Postmaster data, said so, never invented.
    postmaster_client_id: str = field(default_factory=lambda: os.environ.get("POSTMASTER_CLIENT_ID", ""))
    postmaster_client_secret: str = field(default_factory=lambda: os.environ.get("POSTMASTER_CLIENT_SECRET", ""))
    postmaster_refresh_token: str = field(default_factory=lambda: os.environ.get("POSTMASTER_REFRESH_TOKEN", ""))
    worker_inline: bool = field(default_factory=lambda: not _flag("NO_WORKER"))

    def validate(self) -> None:
        if self.live_send and self.auth_mode == "demo":
            raise SystemExit("LIVE_SEND=1 needs a real AUTH_MODE (header). Refusing to start.")
        if self.live_send and self.mode != "live":
            raise SystemExit("LIVE_SEND=1 needs MODE=live. Refusing to start.")
        if self.public_demo and self.live_send:
            raise SystemExit("The public demo never sends. Unset LIVE_SEND.")
        if self.mode == "live" and not self.webhook_secret_set:
            raise SystemExit("MODE=live needs WEBHOOK_SECRET set. Refusing to start.")
        if self.auth_mode == "header" and not (self.access_team_domain and self.access_aud):
            raise SystemExit("AUTH_MODE=header needs CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD to verify the signed token.")


CONFIG = Config()
