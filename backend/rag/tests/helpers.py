"""Deterministic test helpers for RAG unit, security, evaluation, and WhatsApp integration tests."""
from __future__ import annotations

import hashlib
import io
import json
import math
from contextlib import contextmanager

from django.contrib.auth import get_user_model

from accounts.models import UserProfile
from companies.models import Company
from rag import conf
from rag.services import answer_generation_service, embedding_service

User = get_user_model()

# Semantic buckets -> deterministic orthogonal axes in 1024-D space so cosine similarity
# behaves realistically for both relevant and irrelevant queries without calling live Bedrock.
_SEMANTIC_BUCKETS = [
    (0, ("business hours", "open", "monday", "saturday", "sunday", "9:00", "7:00", "timings")),
    (1, ("showroom", "located", "address", "gandhi road", "coimbatore", "641001", "கடை", "எங்கே", "காந்தி சாலை")),
    (2, ("warranty", "delivery", "electrical", "plumbing", "free delivery", "5000")),
    (3, ("steel bolt m10", "m10", "18.00", "18 inr")),
    (4, ("steel bolt m8", "m8", "12.50", "12.5")),
    (5, ("copper wire", "2mm", "240", "per metre")),
    (6, ("pvc pipe", "95")),
    (7, ("upi", "payment", "பணம்", "ரொக்கம்", "வங்கி")),
    (8, ("annual maintenance", "amc", "4500", "maintenance contract")),
    (9, ("conflict_topic", "minimum order", "moq")),
    (10, ("secret_company_b", "quantum turbine", "99999")),
]


def deterministic_vector(text: str, dim: int = 1024) -> list[float]:
    low = (text or "").lower()
    vec = [0.0] * dim
    matched_any = False
    for axis, keywords in _SEMANTIC_BUCKETS:
        hits = sum(1 for kw in keywords if kw in low)
        if hits:
            matched_any = True
            # Spread across 8 dimensions per bucket for smooth cosine scores
            base = axis * 8
            for offset in range(8):
                vec[base + offset] += float(hits)
    if not matched_any:
        # Unrelated text -> hash into higher dimensions [200..dim) so its cosine similarity
        # with every known KB bucket [0..160) is ~0.0.
        digest = hashlib.sha256(low.encode("utf-8")).digest()
        for i, b in enumerate(digest):
            idx = 200 + ((i * 17 + b) % (dim - 200))
            vec[idx] += (b / 255.0) + 0.1
    else:
        # Small deterministic fingerprint in [160..199)
        digest = hashlib.md5(low.encode("utf-8")).digest()
        for i in range(4):
            vec[160 + (digest[i] % 35)] += 0.05

    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class FakeBedrockClient:
    def __init__(self, *, dim: int = 1024, fail_times: int = 0, error_code: str = "ThrottlingException"):
        self.dim = dim
        self.fail_times = fail_times
        self.error_code = error_code
        self.calls = 0

    def invoke_model(self, *, modelId, body, contentType, accept):
        self.calls += 1
        if self.calls <= self.fail_times:
            exc = Exception(self.error_code)
            exc.response = {"Error": {"Code": self.error_code}}
            raise exc
        payload = json.loads(body)
        text = payload.get("inputText", "")
        dim = int(payload.get("dimensions") or self.dim)
        vec = deterministic_vector(text, dim=dim)
        raw = json.dumps({"embedding": vec}).encode("utf-8")
        return {"body": io.BytesIO(raw)}


@contextmanager
def patched_Subsystems(*, bedrock_client=None, gemini_transport=None):
    old_factory = embedding_service._client_factory
    old_transport = answer_generation_service._transport
    client = bedrock_client or FakeBedrockClient()
    embedding_service._client_factory = lambda: client
    if gemini_transport is not None:
        answer_generation_service._transport = gemini_transport
    try:
        yield client
    finally:
        embedding_service._client_factory = old_factory
        answer_generation_service._transport = old_transport
        embedding_service.reset_client_cache()


def make_user(username: str, role: str = "LQ", company: Company | None = None, is_superuser: bool = False):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="TestPassword123!",
        is_superuser=is_superuser,
        is_staff=is_superuser,
    )
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.role = role
    profile.company = company
    profile.save()
    return user
