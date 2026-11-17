"""Django signals emitted by the WhatsApp module for decoupled consumers (e.g. whatsapp_ai)."""

from django.dispatch import Signal

# Emitted after an inbound or outbound WhatsAppMessage is persisted via webhook/sync.
# Arguments: sender, session, conversation, message, is_from_me, is_history_sync
whatsapp_message_persisted = Signal()
