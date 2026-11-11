"""
WhatsApp Conversation Data Cleanup Script
=========================================
Deletes ALL WhatsApp conversation/message/event/recording data.
Does NOT delete WhatsAppSession records, user accounts, or any other app data.

Run with:
    python cleanup_whatsapp_data.py

This script uses the default Django settings (pointing to the production Supabase DB).
"""
import os
import sys
import django

# Ensure we're in the backend directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django.setup()

from whatsapp.models import (
    WhatsAppMessage,
    WhatsAppConversation,
    WhatsAppEvent,
    WhatsAppCallRecording,
)

def main():
    print("=" * 60)
    print("WhatsApp Conversation Data Cleanup")
    print("=" * 60)
    print()

    # Count before deletion
    msg_count = WhatsAppMessage.objects.count()
    conv_count = WhatsAppConversation.objects.count()
    event_count = WhatsAppEvent.objects.count()
    rec_count = WhatsAppCallRecording.objects.count()

    print("BEFORE CLEANUP:")
    print(f"  Messages:      {msg_count}")
    print(f"  Conversations: {conv_count}")
    print(f"  Events:        {event_count}")
    print(f"  Recordings:    {rec_count}")
    print()

    if msg_count + conv_count + event_count + rec_count == 0:
        print("Nothing to delete. All WhatsApp conversation tables are already empty.")
        return

    confirm = input("Delete ALL WhatsApp conversation/message/event/recording data? [yes/no]: ").strip().lower()
    if confirm != "yes":
        print("Aborted. No data deleted.")
        return

    print()
    print("Deleting...")

    # Delete in dependency order (messages before conversations)
    deleted_msgs, _ = WhatsAppMessage.objects.all().delete()
    print(f"  Deleted {deleted_msgs} message records.")

    deleted_convs, _ = WhatsAppConversation.objects.all().delete()
    print(f"  Deleted {deleted_convs} conversation records.")

    deleted_events, _ = WhatsAppEvent.objects.all().delete()
    print(f"  Deleted {deleted_events} event records.")

    deleted_recs, _ = WhatsAppCallRecording.objects.all().delete()
    print(f"  Deleted {deleted_recs} call recording records.")

    # Also clear any temp call state cache files from OS temp dir
    import tempfile
    import glob
    tmp = tempfile.gettempdir()
    removed_files = 0
    for pattern in ["waha_active_call_*.json", "waha_call_state_*.json"]:
        for f in glob.glob(os.path.join(tmp, pattern)):
            try:
                os.remove(f)
                removed_files += 1
            except OSError:
                pass
    if removed_files:
        print(f"  Cleared {removed_files} temp call state cache files from {tmp}.")

    print()
    print("AFTER CLEANUP:")
    print(f"  Messages:      {WhatsAppMessage.objects.count()}")
    print(f"  Conversations: {WhatsAppConversation.objects.count()}")
    print(f"  Events:        {WhatsAppEvent.objects.count()}")
    print(f"  Recordings:    {WhatsAppCallRecording.objects.count()}")
    print()
    print("Cleanup complete. WhatsApp sessions, users and all other app data preserved.")
    print("=" * 60)

if __name__ == "__main__":
    main()
