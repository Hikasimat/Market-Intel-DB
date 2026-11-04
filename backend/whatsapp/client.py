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
import re
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
            return max(2, min(int(os.environ.get("WHATSAPP_SERVICE_TIMEOUT", "4")), 10))
        except ValueError:
            return 4

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[dict] = None,
        query: Optional[dict] = None,
        timeout: Optional[float] = None,
        extra_headers: Optional[dict] = None,
    ) -> tuple[int, Any]:
        """
        Execute an authenticated HTTP request to WAHA.

        Returns (status_code, response_body).
        Raises WAHAServiceError on network or HTTP errors.
        """
        effective_timeout = timeout if timeout is not None else self._timeout
        url = urljoin(self._base_url + "/", path.lstrip("/"))

        if query:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(query)}"

        headers = {
            # WAHA expects X-Api-Key with the plaintext key.
            "X-Api-Key": self._api_key,
            "Accept": "application/json, image/*, */*",
        }

        if extra_headers:
            headers.update(extra_headers)

        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url=url, method=method, data=body, headers=headers)

        try:
            with urlopen(request, timeout=effective_timeout) as response:
                content_type = (response.headers.get("Content-Type") or "").lower()
                raw_bytes = response.read()

                # If WAHA returns an image binary stream (e.g. GET /api/{session}/auth/qr returning image/png)
                if "image/" in content_type:
                    import base64
                    clean_ct = content_type.split(";")[0].strip() or "image/png"
                    b64 = base64.b64encode(raw_bytes).decode("ascii")
                    return response.status, {
                        "qrBase64": f"data:{clean_ct};base64,{b64}",
                        "qr": f"data:{clean_ct};base64,{b64}",
                        "format": "image",
                    }

                try:
                    raw = raw_bytes.decode("utf-8")
                    parsed = json.loads(raw) if raw.strip() else {}
                    return response.status, parsed
                except (UnicodeDecodeError, json.JSONDecodeError):
                    import base64
                    b64 = base64.b64encode(raw_bytes).decode("ascii")
                    return response.status, {
                        "qrBase64": f"data:image/png;base64,{b64}",
                        "qr": f"data:image/png;base64,{b64}",
                        "format": "image",
                    }

        except HTTPError as exc:
            raw = exc.read().decode("utf-8") if exc.fp else ""
            try:
                detail = json.loads(raw)
            except json.JSONDecodeError:
                detail = {"detail": raw or "WAHA returned an error."}

            # Log without exposing the API key (silence benign probes that 404 on noweb-light).
            is_benign_404 = exc.code == 404 and (
                path == "/api/chats"
                or path.startswith(("/api/chats/", "/api/groups/"))
                or path in ("/api/groups",)
            )
            if is_benign_404:
                logger.debug(
                    "WAHA probe 404 (benign/unsupported route): method=%s path=%s",
                    method,
                    path,
                )
            else:
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
            # Fallback for Docker container accessing host WAHA
            reason_str = str(exc.reason).lower()
            if ("connection refused" in reason_str or "errno 111" in reason_str) and ("localhost:3000" in url or "127.0.0.1:3000" in url):
                for fallback_host in ("host.docker.internal:3000", "172.17.0.1:3000"):
                    try:
                        alt_url = url.replace("localhost:3000", fallback_host).replace("127.0.0.1:3000", fallback_host)
                        alt_req = Request(url=alt_url, method=method, data=body, headers=headers)
                        with urlopen(alt_req, timeout=min(2.0, effective_timeout)) as alt_resp:
                            logger.info("WAHA fallback succeeded on %s", fallback_host)
                            raw_bytes = alt_resp.read()
                            ct = (alt_resp.headers.get("Content-Type") or "").lower()
                            if "image/" in ct:
                                import base64
                                clean_ct = ct.split(";")[0].strip() or "image/png"
                                b64 = base64.b64encode(raw_bytes).decode("ascii")
                                return alt_resp.status, {"qrBase64": f"data:{clean_ct};base64,{b64}", "qr": f"data:{clean_ct};base64,{b64}", "format": "image"}
                            try:
                                return alt_resp.status, json.loads(raw_bytes.decode("utf-8"))
                            except Exception:
                                import base64
                                b64 = base64.b64encode(raw_bytes).decode("ascii")
                                return alt_resp.status, {"qrBase64": f"data:image/png;base64,{b64}", "qr": f"data:image/png;base64,{b64}", "format": "image"}
                    except Exception:
                        pass

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
                effective_timeout,
            )
            raise WAHAServiceError(
                f"WAHA request timed out after {effective_timeout}s.",
                status_code=504,
            )

    # -----------------------------------------------------------------------
    # Public API methods — clean abstraction over WAHA endpoints
    # -----------------------------------------------------------------------

    def health(self) -> dict:
        """Check WAHA health (unauthenticated endpoint)."""
        _status, body = self._request("GET", "/health", timeout=2.0)
        return body

    # -- Session management --------------------------------------------------

    def start_session(self, session_name: str = "default") -> dict:
        """Start a WAHA session."""
        _status, body = self._request(
            "POST",
            f"/api/sessions/{session_name}/start",
            timeout=3.5,
        )
        return body

    def stop_session(self, session_name: str = "default") -> dict:
        """Stop a WAHA session (does not log out WhatsApp)."""
        _status, body = self._request(
            "POST",
            f"/api/sessions/{session_name}/stop",
            timeout=3.5,
        )
        return body

    def logout_session(self, session_name: str = "default") -> dict:
        """Logout from WhatsApp and clear the session."""
        _status, body = self._request(
            "POST",
            f"/api/sessions/{session_name}/logout",
            timeout=3.5,
        )
        return body

    def delete_session(self, session_name: str = "default") -> None:
        """Delete a WAHA session and wipe its directory."""
        self._request(
            "DELETE",
            f"/api/sessions/{session_name}",
            timeout=3.0,
        )

    def get_session_status(self, session_name: str = "default") -> dict:
        """Get the current state of a WAHA session."""
        _status, body = self._request(
            "GET",
            f"/api/sessions/{session_name}",
            timeout=2.5,
        )
        return body

    def get_all_sessions(self) -> list:
        """List all WAHA sessions."""
        _status, body = self._request("GET", "/api/sessions", timeout=2.5)
        return body if isinstance(body, list) else []

    def get_qr(self, session_name: str = "default") -> dict:
        """Get the QR code for a session (as base64 or raw string)."""
        try:
            _status, body = self._request(
                "GET",
                f"/api/{session_name}/auth/qr",
                timeout=2.5,
            )
            if isinstance(body, dict):
                # 1. WAHA JSON format: {"mimetype": "image/png", "data": "base64..."}
                b64 = body.get("data") or body.get("qrBase64") or ""
                if b64:
                    mimetype = body.get("mimetype") or "image/png"
                    prefix = f"data:{mimetype};base64," if not str(b64).startswith("data:") else ""
                    body["qrBase64"] = f"{prefix}{b64}"
                    body["qr"] = f"{prefix}{b64}"
                    body["value"] = body.get("value") or f"{prefix}{b64}"
                # 2. WAHA raw value: {"value": "2@..."}
                elif body.get("value"):
                    val = str(body["value"])
                    body["qr"] = val
                    body["qrBase64"] = val if val.startswith("data:") else ""
            return body if isinstance(body, dict) else {}
        except Exception as exc:
            logger.debug("WAHA get_qr error for %s: %s", session_name, exc)
            return {}

    def request_code(self, session_name: str, phone_number: str) -> dict:
        """Request 8-character pairing code for phone-number linking."""
        _status, body = self._request(
            "POST",
            f"/api/{session_name}/auth/request-code",
            payload={"phoneNumber": phone_number},
            timeout=4.0,
        )
        return body

    def dispatch_qr(self, session_name: str = "default") -> dict:
        """Safe no-op helper for backward compatibility."""
        return {}

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

    def get_groups(self, session_name: str = "default") -> list:
        """Get list of participating groups from WAHA noweb-light."""
        try:
            _status, body = self._request(
                "GET",
                f"/api/{session_name}/groups",
                timeout=5.0,
            )
            return body if isinstance(body, list) else []
        except Exception as e:
            logger.debug("Failed to get groups from WAHA for session %s: %s", session_name, e)
            return []

    def get_chats(self, session_name: str = "default", limit: int = 50) -> list:
        """Get list of chats / groups from WAHA noweb-light."""
        return self.get_groups(session_name)

    def get_messages(
        self,
        session_name: str,
        chat_id: str,
        limit: int = 50,
    ) -> list:
        """Get messages for a specific chat."""
        try:
            _status, body = self._request(
                "GET",
                f"/api/chats/{chat_id}/messages",
                query={"session": session_name, "limit": min(limit, 100)},
            )
            return body if isinstance(body, list) else []
        except WAHAServiceError as exc:
            if exc.status_code == 404:
                return []
            raise
        except Exception:
            return []

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

    # -- Groups --------------------------------------------------------------

    def create_group(self, session_name: str, name: str, participants: list) -> dict:
        """Create a WhatsApp group with participants."""
        formatted_obj_participants = []
        formatted_str_participants = []
        for p in participants:
            digits = re.sub(r"\D+", "", str(p))
            if digits:
                formatted_obj_participants.append({"id": f"{digits}@c.us"})
                formatted_str_participants.append(f"{digits}@c.us")

        payload_obj = {
            "name": name,
            "participants": formatted_obj_participants,
        }
        payload_str = {
            "name": name,
            "participants": formatted_str_participants,
        }

        # Try session endpoint then global endpoint with both schemas
        sessions_to_try = [session_name]
        if session_name != "default":
            sessions_to_try.append("default")

        last_error = None
        for sess in sessions_to_try:
            for p_load in (payload_obj, payload_str):
                try:
                    _status, body = self._request(
                        "POST",
                        f"/api/{sess}/groups",
                        payload=p_load,
                        timeout=12.0,
                    )
                    if isinstance(body, dict) and (body.get("id") or body.get("gid") or body.get("chatId") or body.get("groupJid")):
                        return body
                except Exception as e:
                    last_error = e

                try:
                    p_load_with_sess = dict(p_load)
                    p_load_with_sess["session"] = sess
                    _status, body = self._request(
                        "POST",
                        "/api/groups",
                        payload=p_load_with_sess,
                        timeout=12.0,
                    )
                    if isinstance(body, dict) and (body.get("id") or body.get("gid") or body.get("chatId") or body.get("groupJid")):
                        return body
                except Exception as e:
                    last_error = e

        if last_error:
            # If 404 (endpoint not supported by WAHA engine)
            if isinstance(last_error, WAHAServiceError) and (last_error.status_code == 404 or "404" in str(last_error)):
                raise WAHAServiceError(
                    "WhatsApp group creation via API is not supported by the WAHA Noweb engine. "
                    "Please create the group in your WhatsApp mobile app; it will automatically synchronize to your conversations list here.",
                    status_code=404,
                )
            raise last_error
        return {}

    def get_group_info(self, session_name: str, group_id: str) -> dict:
        """Get group details and participants from WAHA."""
        try:
            _status, body = self._request(
                "GET",
                f"/api/{session_name}/groups/{group_id}",
                timeout=4.0,
            )
            return body if isinstance(body, dict) else {}
        except Exception:
            _status, body = self._request(
                "GET",
                f"/api/groups/{group_id}",
                query={"session": session_name},
                timeout=4.0,
            )
            return body if isinstance(body, dict) else {}

    # -- Voice Calling (WAHA Live Calling API) -------------------------------

    def resolve_calling_session(self, preferred_session: str = "default") -> str:
        """
        Dynamically determine the active WAHA calling session that is paired.
        Checks candidate sessions in order:
          1. preferred_session (e.g. user's own session)
          2. Any working session from get_all_sessions()
          3. 'default'
        Returns the first session name reporting paired == True.
        If none reports paired == True, returns the first working session, 'default', or preferred_session.
        """
        candidates = []
        if preferred_session:
            candidates.append(preferred_session)

        # Check working sessions from WAHA
        try:
            sessions = self.get_all_sessions()
            if isinstance(sessions, list):
                for s in sessions:
                    if isinstance(s, dict) and s.get("status") == "WORKING":
                        w_name = s.get("name")
                        if w_name and w_name not in candidates:
                            candidates.append(w_name)
                for s in sessions:
                    if isinstance(s, dict):
                        w_name = s.get("name")
                        if w_name and w_name not in candidates:
                            candidates.append(w_name)
        except Exception as e:
            logger.debug("Failed to list WAHA sessions during calling resolution: %s", e)

        if "default" not in candidates:
            candidates.append("default")

        for sess in candidates:
            try:
                _status, body = self._request(
                    "GET",
                    f"/api/calling/sessions/{sess}/status",
                    timeout=3.0,
                )
                if isinstance(body, dict) and body.get("paired") is True:
                    logger.info("Resolved paired calling session: %s", sess)
                    return sess
            except Exception:
                continue

        # If none reported paired in calling subsystem, prefer any actively WORKING Baileys session
        working_sessions = []
        try:
            sessions = self.get_all_sessions()
            if isinstance(sessions, list):
                for s in sessions:
                    if isinstance(s, dict) and s.get("status") == "WORKING":
                        w_name = s.get("name")
                        if w_name and w_name not in working_sessions:
                            working_sessions.append(w_name)
        except Exception:
            pass

        if working_sessions:
            if preferred_session in working_sessions:
                return preferred_session
            return working_sessions[0]

        return candidates[0] if candidates else (preferred_session or "default")

    def pair_calling(self, session_name: str) -> dict:
        """Initiate pairing for calling subsystem."""
        try:
            _status, body = self._request(
                "POST",
                f"/api/calling/sessions/{session_name}/pair",
                timeout=5.0,
            )
            return body if isinstance(body, dict) else {}
        except Exception as e:
            logger.warning("Failed to initiate calling pairing for %s: %s", session_name, e)
            return {"error": str(e)}

    def get_calling_qr(self, session_name: str) -> dict:
        """Fetch pairing QR code for calling subsystem."""
        try:
            _status, body = self._request(
                "GET",
                f"/api/calling/sessions/{session_name}/qr",
                timeout=5.0,
            )
            return body if isinstance(body, dict) else {}
        except Exception as e:
            logger.debug("Failed to fetch calling QR for %s: %s", session_name, e)
            return {"error": str(e)}

    def get_calling_status(self, session_name: str) -> dict:
        """Query status of calling subsystem for given session, falling back to paired session."""
        target_session = self.resolve_calling_session(preferred_session=session_name)
        candidates = [target_session]
        if session_name not in candidates:
            candidates.append(session_name)
        if "default" not in candidates:
            candidates.append("default")

        for sess in candidates:
            try:
                _status, body = self._request(
                    "GET",
                    f"/api/calling/sessions/{sess}/status",
                    timeout=4.0,
                )
                if isinstance(body, dict):
                    if body.get("paired") is True or sess == candidates[-1]:
                        body["resolved_session"] = sess
                        return body
            except Exception as e:
                logger.debug("Query calling status failed for session '%s': %s", sess, e)

        return {"enabled": False, "paired": False, "state": "error", "error": "No calling session available"}

    def start_call(self, session_name: str, phone: str, client_id: Optional[str] = None) -> dict:
        """Initiate outgoing voice call to a WhatsApp phone number via paired calling session."""
        extra_headers = {}
        if client_id:
            extra_headers["X-Client-Id"] = client_id

        clean_phone = re.sub(r"\D+", "", phone)
        payload = {"phone": clean_phone}

        target_session = self.resolve_calling_session(preferred_session=session_name)
        candidates = [target_session]
        if session_name not in candidates:
            candidates.append(session_name)
        if "default" not in candidates:
            candidates.append("default")

        try:
            sessions = self.get_all_sessions()
            if isinstance(sessions, list):
                for s in sessions:
                    if isinstance(s, dict) and s.get("status") == "WORKING":
                        w_name = s.get("name")
                        if w_name and w_name not in candidates:
                            candidates.append(w_name)
        except Exception:
            pass

        last_error = None
        for sess in candidates:
            try:
                _status, body = self._request(
                    "POST",
                    f"/api/calling/sessions/{sess}/calls",
                    payload=payload,
                    extra_headers=extra_headers,
                    timeout=10.0,
                )
                if isinstance(body, dict):
                    body["session_name"] = sess
                    return body
            except Exception as e:
                last_error = e
                logger.info("start_call attempt failed for session '%s': %s", sess, e)
                continue

        err_msg = str(last_error) if last_error else "Calling session is not paired."
        raise WAHAServiceError(f"Failed to start call: {err_msg}")

    def accept_call(self, session_name: str, call_id: str, client_id: Optional[str] = None) -> dict:
        """Accept an incoming voice call."""
        extra_headers = {}
        if client_id:
            extra_headers["X-Client-Id"] = client_id

        target_session = self.resolve_calling_session(preferred_session=session_name)
        candidates = [target_session]
        if session_name not in candidates:
            candidates.append(session_name)
        if "default" not in candidates:
            candidates.append("default")

        last_error = None
        for sess in candidates:
            try:
                _status, body = self._request(
                    "POST",
                    f"/api/calling/sessions/{sess}/calls/{call_id}/accept",
                    extra_headers=extra_headers,
                    timeout=8.0,
                )
                if isinstance(body, dict):
                    body["session_name"] = sess
                    return body
            except Exception as e:
                last_error = e

        raise WAHAServiceError(f"Failed to accept call: {last_error}")

    def reject_call(self, session_name: str, call_id: str) -> dict:
        """Reject an incoming voice call."""
        target_session = self.resolve_calling_session(preferred_session=session_name)
        candidates = [target_session]
        if session_name not in candidates:
            candidates.append(session_name)
        if "default" not in candidates:
            candidates.append("default")

        last_error = None
        for sess in candidates:
            try:
                _status, body = self._request(
                    "POST",
                    f"/api/calling/sessions/{sess}/calls/{call_id}/reject",
                    timeout=6.0,
                )
                if isinstance(body, dict):
                    return body
            except Exception as e:
                last_error = e

        raise WAHAServiceError(f"Failed to reject call: {last_error}")

    def end_call(self, session_name: str, call_id: str) -> dict:
        """Hang up / terminate an active voice call."""
        target_session = self.resolve_calling_session(preferred_session=session_name)
        candidates = [target_session]
        if session_name not in candidates:
            candidates.append(session_name)
        if "default" not in candidates:
            candidates.append("default")

        for sess in candidates:
            try:
                _status, body = self._request(
                    "DELETE",
                    f"/api/calling/sessions/{sess}/calls/{call_id}",
                    timeout=6.0,
                )
                if isinstance(body, dict):
                    return body
            except Exception:
                continue

        return {"status": "ended"}

    def exchange_webrtc(self, session_name: str, call_id: str, sdp_offer: str) -> dict:
        """Exchange WebRTC SDP offer to establish PCM audio data channel."""
        payload = {"sdp_offer": sdp_offer}
        target_session = self.resolve_calling_session(preferred_session=session_name)
        candidates = [target_session]
        if session_name not in candidates:
            candidates.append(session_name)
        if "default" not in candidates:
            candidates.append("default")

        last_error = None
        for sess in candidates:
            try:
                _status, body = self._request(
                    "POST",
                    f"/api/calling/sessions/{sess}/calls/{call_id}/webrtc",
                    payload=payload,
                    timeout=12.0,
                )
                if isinstance(body, dict):
                    return body
            except Exception as e:
                last_error = e
                logger.info("exchange_webrtc attempt failed for session '%s': %s", sess, e)
                continue

        raise WAHAServiceError(f"Failed to exchange WebRTC offer: {last_error}")

    def get_calling_history(self, session_name: str) -> list:
        """Get voice call history from WAHA calling service."""
        target_session = self.resolve_calling_session(preferred_session=session_name)
        candidates = [target_session]
        if session_name not in candidates:
            candidates.append(session_name)
        if "default" not in candidates:
            candidates.append("default")

        for sess in candidates:
            try:
                _status, body = self._request(
                    "GET",
                    f"/api/calling/sessions/{sess}/history",
                    timeout=6.0,
                )
                if isinstance(body, list):
                    return body
            except Exception:
                continue

        return []


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
