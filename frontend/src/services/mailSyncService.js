import { resetMailboxCache } from './cache/inboxCacheService';

const CHANNEL_NAME = 'marketintel_mail_sync';
const STORAGE_KEY = 'marketintel_mail_event';

let channel = null;
try {
  if (typeof window !== 'undefined' && 'BroadcastChannel' in window) {
    channel = new BroadcastChannel(CHANNEL_NAME);
  }
} catch (e) {
  channel = null;
}

/**
 * Broadcast an email event to all components, pages, and browser tabs.
 * @param {string} type - Event type (e.g. 'MAIL_SENT', 'MAIL_RECEIVED', 'DRAFT_SAVED', 'MAIL_MUTATED')
 * @param {Object} details - Additional payload
 */
export function broadcastMailEvent(type, details = {}) {
  const eventPayload = {
    type,
    ...details,
    timestamp: Date.now(),
  };

  // 1. BroadcastChannel for cross-tab messaging
  if (channel) {
    try {
      channel.postMessage(eventPayload);
    } catch (e) {
      // Ignore postMessage errors
    }
  }

  // 2. localStorage event fallback for cross-tab
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(eventPayload));
  } catch (e) {
    // Ignore storage quota / incognito errors
  }

  // 3. Same-window custom event
  try {
    window.dispatchEvent(new CustomEvent('marketintel_mail_event', { detail: eventPayload }));
  } catch (e) {
    // Ignore
  }
}

/**
 * Subscribe to mail sync events across tabs and components.
 * @param {Function} callback - Called with event payload
 * @returns {Function} unsubscribe cleanup function
 */
export function subscribeMailEvents(callback) {
  if (typeof window === 'undefined') return () => {};

  const handleBroadcast = (event) => {
    if (event && event.data) {
      callback(event.data);
    }
  };

  const handleStorage = (event) => {
    if (event.key === STORAGE_KEY && event.newValue) {
      try {
        const parsed = JSON.parse(event.newValue);
        callback(parsed);
      } catch (e) {
        // Ignore JSON parse errors
      }
    }
  };

  const handleWindow = (event) => {
    if (event && event.detail) {
      callback(event.detail);
    }
  };

  if (channel) {
    channel.addEventListener('message', handleBroadcast);
  }
  window.addEventListener('storage', handleStorage);
  window.addEventListener('marketintel_mail_event', handleWindow);

  return () => {
    if (channel) {
      channel.removeEventListener('message', handleBroadcast);
    }
    window.removeEventListener('storage', handleStorage);
    window.removeEventListener('marketintel_mail_event', handleWindow);
  };
}

/**
 * Invalidate cached SENT and DRAFT mailboxes and notify all tabs/components immediately.
 * @param {string|number} [userId]
 * @param {string|number} [mailAccountId]
 */
export async function notifyMailSent(userId, mailAccountId = 'default') {
  if (userId) {
    try {
      await resetMailboxCache(userId, mailAccountId, 'SENT');
      await resetMailboxCache(userId, mailAccountId, 'DRAFT');
    } catch (e) {
      // Non-fatal
    }
  }
  broadcastMailEvent('MAIL_SENT', { folder: 'SENT' });
}
