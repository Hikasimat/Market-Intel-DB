"""
backend/whatsapp/client.py

Low-level WAHA HTTP client.

Responsibilities:
  - Authenticates all requests to WAHA with X-Api-Key header.
  - Validates configuration at startup (requires WHATSAPP_SERVICE_URL
    and WHATSAPP_SERVICE_API_KEY to be set).
  - Raises WAHAServiceError on connection failures.
  - Never logs the API key.
  - Enforces a configurable request timeout.
  - Does NOT contain any business logic (that lives in services.py).

The WAHA API key is the PLAINTEXT key that corresponds to the sha512 hash
stored in the WAHA container .env. Django sends the plaintext key in
X-Api-Key; WAHA validates it against the stored hash.
"""

import json
import logging
import os
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class WAHAServiceError(Exception):
    """Raised when WAHA returns an error or is unreachable."""

    def __init__(self, message: str, status_code: int = 503, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or {}


class WAHAAuthError(WAHAServiceError):
    """Raised when WAHA returns 401 (invalid API key)."""
    pass


class WAHAClient:
    """
    Authenticated HTTP client for the WAHA WhatsApp API.

    All methods return the parsed JSON response body.
    They raise WAHAServiceError on HTTP or network errors.
    """

    def __init__(self):
        # Read env at init but also re-read on each request via properties.
        # This avoids issues with stale config when env vars change.
        pass

    @property
    def _base_url(self) -> str:
        return self._get_base_url()

    @property
    def _api_key(self) -> str:
        return self._get_api_key()

    @property
    def _timeout(self) -> int:
        return self._get_timeout()

    @staticmethod
    def _get_base_url() -> str:
        url = os.environ.get("WHATSAPP_SERVICE_URL", "").rstrip("/")
        if not url:
            raise RuntimeError(
                "WHATSAPP_SERVICE_URL is not configured. "
                "Set it to the HTTPS URL of the Oracle WAHA service."
            )
        if not url.startswith(("https://", "http://")):
            raise RuntimeError(
                f"WHATSAPP_SERVICE_URL must start with https:// (got: {url!r})"
            )
        return url

    @staticmethod
    def _get_api_key() -> str:
        key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "").strip()
        if not key:
            raise RuntimeError("WHATSAPP_SERVICE_API_KEY is not configured.")
        return key

    @staticmethod
    def _get_timeout() -> int:
        try:
            return max(5, int(os.environ.get("WHATSAPP_SERVICE_TIMEOUT", "30")))
        except ValueError:
            return 30

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[dict] = None,
        query: Optional[dict] = None,
    ) -> tuple[int, Any]:
        """
        Execute an authenticated HTTP request to WAHA.

        Returns (status_code, response_body).
        Raises WAHAServiceError on network or HTTP errors.
        """
        url = urljoin(self._base_url + "/", path.lstrip("/"))

        if query:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(query)}"

        headers = {
            # WAHA expects X-Api-Key with the plaintext key.
            "X-Api-Key": self._api_key,
            "Accept": "application/json",
        }

        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url=url, method=method, data=body, headers=headers)

        try:
            with urlopen(request, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw) if raw.strip() else {}
                return response.status, parsed

        except HTTPError as exc:
            raw = exc.read().decode("utf-8") if exc.fp else ""
            try:
                detail = json.loads(raw)
            except json.JSONDecodeError:
                detail = {"detail": raw or "WAHA returned an error."}

            # Log without exposing the API key.
            logger.warning(
                "WAHA HTTP error: method=%s path=%s status=%d payload=%s detail=%s",
                method,
                path,
                exc.code,
                payload,
                detail,
                extra={"status_code": exc.code},
            )

            if exc.code == 401:
                raise WAHAAuthError(
                    "WAHA authentication failed. Check WHATSAPP_SERVICE_API_KEY.",
                    status_code=401,
                    detail=detail,
                )

            raise WAHAServiceError(
                f"WAHA returned HTTP {exc.code} for {method} {path}. Detail: {detail}",
                status_code=exc.code,
                detail=detail,
            )

        except URLError as exc:
            logger.error(
                "WAHA unreachable: method=%s path=%s reason=%s",
                method,
                path,
                str(exc.reason),
            )
            raise WAHAServiceError(
                f"WAHA service is unreachable: {exc.reason}",
                status_code=503,
            ) from exc

        except TimeoutError:
            logger.error(
                "WAHA request timeout: method=%s path=%s timeout=%ds",
                method,
                path,
                self._timeout,
            )
            raise WAHAServiceError(
                f"WAHA request timed out after {self._timeout}s.",
                status_code=504,
            )

    # -----------------------------------------------------------------------
    # Public API methods — clean abstraction over WAHA endpoints
    # -----------------------------------------------------------------------

    def health(self) -> dict:
        """Check WAHA health (unauthenticated endpoint)."""
        _status, body = self._request("GET", "/health")
        return body

    # -- Session management --------------------------------------------------

    def start_session(self, session_name: str = "default") -> dict:
        """Start a WAHA session."""
        _status, body = self._request(
            "POST",
            f"/api/sessions/{session_name}/start",
        )
        return body

    def stop_session(self, session_name: str = "default") -> dict:
        """Stop a WAHA session (does not log out WhatsApp)."""
        _status, body = self._request(
            "POST",
            f"/api/sessions/{session_name}/stop",
        )
        return body

    def logout_session(self, session_name: str = "default") -> dict:
        """Logout from WhatsApp and clear the session."""
        _status, body = self._request(
            "POST",
            f"/api/sessions/{session_name}/logout",
        )
        return body

    def delete_session(self, session_name: str = "default") -> None:
        """Delete a WAHA session and wipe its directory."""
        self._request(
            "DELETE",
            f"/api/sessions/{session_name}",
        )

    def get_session_status(self, session_name: str = "default") -> dict:
        """Get the current state of a WAHA session."""
        _status, body = self._request(
            "GET",
            f"/api/sessions/{session_name}",
        )
        return body

    def get_all_sessions(self) -> list:
        """List all WAHA sessions."""
        _status, body = self._request("GET", "/api/sessions")
        return body if isinstance(body, list) else []

    def get_qr(self, session_name: str = "default") -> dict:
        """Get the QR code for a session (as image bytes or data URL)."""
        _status, body = self._request(
            "GET",
            f"/api/{session_name}/auth/qr",
        )
        return body

    def request_code(self, session_name: str, phone_number: str) -> dict:
        """Request 8-character pairing code for phone-number linking."""
        _status, body = self._request(
            "POST",
            f"/api/{session_name}/auth/request-code",
            payload={"phoneNumber": phone_number},
        )
        return body

    def dispatch_qr(self, session_name: str = "default") -> dict:
        """Force re-dispatch of QR code via webhook."""
        _status, body = self._request(
            "POST",
            f"/api/{session_name}/auth/qr/dispatch",
        )
        return body

    # -- Messaging -----------------------------------------------------------

    def send_text(
        self,
        session_name: str,
        chat_id: str,
        text: str,
        reply_to: str = None,
    ) -> dict:
        """
        Send a plain-text WhatsApp message.

        Args:
            session_name: WAHA session name.
            chat_id:      WhatsApp chat ID (e.g., "919876543210@c.us").
            text:         Message body (max 4096 chars).
            reply_to:     Optional WAHA message ID to reply to.

        Returns:
            WAHA response with message ID.
        """
        payload = {
            "session": session_name,
            "chatId": chat_id,
            "text": text,
        }
        if reply_to:
            payload["reply_to"] = reply_to
            # WAHA quirk: when reply_to is present, session must also be in query string
            endpoint = f"/api/sendText?session={session_name}"
        else:
            endpoint = "/api/sendText"

        _status, body = self._request(
            "POST",
            endpoint,
            payload=payload,
        )
        return body

    def send_image(
        self,
        session_name: str,
        chat_id: str,
        url: str,
        caption: str = "",
        filename: str = "",
    ) -> dict:
        """Send an image message."""
        _status, body = self._request(
            "POST",
            "/api/sendImage",
            payload={
                "session": session_name,
                "chatId": chat_id,
                "file": {"url": url},
                "caption": caption,
                "filename": filename,
            },
        )
        return body

    def send_document(
        self,
        session_name: str,
        chat_id: str,
        url: str,
        filename: str,
        caption: str = "",
    ) -> dict:
        """Send a document/file message."""
        _status, body = self._request(
            "POST",
            "/api/sendFile",
            payload={
                "session": session_name,
                "chatId": chat_id,
                "file": {"url": url},
                "caption": caption,
                "filename": filename,
            },
        )
        return body

    def send_voice(
        self,
        session_name: str,
        chat_id: str,
        file: dict,
    ) -> dict:
        """Send a voice audio note."""
        _status, body = self._request(
            "POST",
            "/api/sendVoice",
            payload={
                "session": session_name,
                "chatId": chat_id,
                "file": file,
            },
        )
        return body

    def send_reaction(
        self,
        session_name: str,
        chat_id: str,
        message_id: str,
        reaction: str,
    ) -> dict:
        """Send an emoji reaction to a message."""
        _status, body = self._request(
            "POST",
            "/api/sendReaction",
            payload={
                "session": session_name,
                "chatId": chat_id,
                "messageId": message_id,
                "reaction": reaction,
            },
        )
        return body

    def check_number_exists(self, phone: str, session_name: str = "default") -> dict:
        """Check if a phone number exists on WhatsApp."""
        _status, body = self._request(
            "GET",
            "/api/contacts/check-exists",
            query={"phone": phone, "session": session_name},
        )
        return body

    # -- Chat / messages -----------------------------------------------------

    def get_chats(self, session_name: str = "default", limit: int = 50) -> list:
        """Get list of chats."""
        _status, body = self._request(
            "GET",
            "/api/chats",
            query={"session": session_name, "limit": limit},
        )
        return body if isinstance(body, list) else []

    def get_messages(
        self,
        session_name: str,
        chat_id: str,
        limit: int = 50,
    ) -> list:
        """Get messages for a specific chat."""
        _status, body = self._request(
            "GET",
            f"/api/chats/{chat_id}/messages",
            query={"session": session_name, "limit": min(limit, 100)},
        )
        return body if isinstance(body, list) else []

    def mark_as_read(self, session_name: str, chat_id: str, message_id: str = None) -> dict:
        """Mark messages in a chat as read via WAHA sendSeen."""
        payload = {"session": session_name, "chatId": chat_id}
        if message_id:
            payload["messageId"] = message_id
        _status, body = self._request(
            "POST",
            "/api/sendSeen",
            payload=payload,
        )
        return body


# ---------------------------------------------------------------------------
# Module-level singleton accessor
# ---------------------------------------------------------------------------
_client_instance: Optional[WAHAClient] = None


def get_waha_client() -> WAHAClient:
    """
    Return a shared WAHAClient instance.

    Raises RuntimeError if WAHA is not configured.
    Raises a specific error if WHATSAPP_ENABLED=false.
    """
    if os.environ.get("WHATSAPP_ENABLED", "false").lower() != "true":
        raise WAHAServiceError(
            "WhatsApp integration is disabled (WHATSAPP_ENABLED=false).",
            status_code=503,
        )

    # Always return a fresh client so env var changes (e.g. tunnel URL rotation)
    # take effect without requiring a server restart.
    return WAHAClient()
