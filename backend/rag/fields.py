"""
Embedding column type.

On PostgreSQL this IS pgvector's `vector(N)` column (pgvector.django.VectorField).
On any other database vendor (only the in-memory SQLite used by the existing unit
tests) it degrades to a TEXT column holding JSON so the app's tables can still be
created. Production and local development always run PostgreSQL + pgvector.
"""
from __future__ import annotations

import json

from pgvector.django import VectorField


class EmbeddingField(VectorField):
    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return super().db_type(connection)
        return "text"

    def get_prep_value(self, value):
        if value is None:
            return None
        if hasattr(value, "tolist"):
            value = value.tolist()
        return "[" + ",".join(repr(float(x)) for x in value) + "]"

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return [float(x) for x in value]
        if isinstance(value, (bytes, bytearray)):
            value = value.decode()
        if isinstance(value, str):
            return [float(x) for x in json.loads(value)]
        return [float(x) for x in value]

    def to_python(self, value):
        if value is None or isinstance(value, list):
            return value
        return self.from_db_value(value, None, None)
