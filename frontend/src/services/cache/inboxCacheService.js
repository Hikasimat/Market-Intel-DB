/**
 * inboxCacheService.js
 *
 * IndexedDB cache layer specific to mailbox data.
 *
 * Stores:
 *  - mail-messages   : per-folder message metadata (keyed by userId:accountId:folder)
 *  - mail-bodies     : full email bodies (keyed by userId:accountId:folder:uid)
 *  - mail-state      : per-folder UIDVALIDITY + highest-known UID + sync timestamp
 *  - notified-emails : Set of UIDs that have already triggered a "new email" popup
 *
 * Cache identity for email bodies uses the stable message UID.
 *
 * UIDVALIDITY handling:
 *   If the server reports a different UIDVALIDITY the cached messages for that
 *   folder are stale and must be discarded before rebuilding.
 */

const DB_NAME = 'marketintel-inbox';
const DB_VERSION = 1;

const STORE_MESSAGES = 'mail-messages';
const STORE_BODIES   = 'mail-bodies';
const STORE_STATE    = 'mail-state';
const STORE_NOTIFIED = 'notified-emails';

/** @type {IDBDatabase|null} */
let _db = null;

/**
 * Open (or reuse) the inbox IndexedDB connection.
 * @returns {Promise<IDBDatabase>}
 */
function openInboxDB() {
  if (_db) return Promise.resolve(_db);

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;

      if (!db.objectStoreNames.contains(STORE_MESSAGES)) {
        // Key: userId:accountId:folder
        db.createObjectStore(STORE_MESSAGES, { keyPath: 'key' });
      }
      if (!db.objectStoreNames.contains(STORE_BODIES)) {
        // Key: userId:accountId:folder:uid
        db.createObjectStore(STORE_BODIES, { keyPath: 'key' });
      }
      if (!db.objectStoreNames.contains(STORE_STATE)) {
        // Key: userId:accountId:folder
        db.createObjectStore(STORE_STATE, { keyPath: 'key' });
      }
      if (!db.objectStoreNames.contains(STORE_NOTIFIED)) {
        // Key: userId:accountId:folder
        db.createObjectStore(STORE_NOTIFIED, { keyPath: 'key' });
      }
    };

    request.onsuccess = (event) => {
      _db = event.target.result;
      resolve(_db);
    };

    request.onerror = (event) => {
      reject(event.target.error);
    };
  });
}

/** Build the standard mailbox key. */
function mailboxKey(userId, mailAccountId, folder) {
  return `${userId}:${mailAccountId}:${folder}`;
}

/** Build the key for a specific email body. */
function bodyKey(userId, mailAccountId, folder, uid) {
  return `${userId}:${mailAccountId}:${folder}:${uid}`;
}

// ─── Message metadata ─────────────────────────────────────────────────────────

/**
 * Get cached message metadata list for a folder.
 *
 * @param {string|number} userId
 * @param {string|number} mailAccountId
 * @param {string}        folder
 * @returns {Promise<Array|null>} array of message objects, or null on miss
 */
export async function getMailboxMessages(userId, mailAccountId, folder) {
  try {
    const db = await openInboxDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_MESSAGES, 'readonly');
      const req = tx.objectStore(STORE_MESSAGES).get(mailboxKey(userId, mailAccountId, folder));
      req.onsuccess = () => resolve(req.result ? req.result.messages : null);
      req.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

/**
 * Store message metadata list for a folder.
 *
 * @param {string|number} userId
 * @param {string|number} mailAccountId
 * @param {string}        folder
 * @param {Array}         messages
 * @param {number|null}   [uidvalidity]
 * @returns {Promise<void>}
 */
export async function setMailboxMessages(userId, mailAccountId, folder, messages, uidvalidity = null) {
  try {
    const db = await openInboxDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_MESSAGES, 'readwrite');
      tx.objectStore(STORE_MESSAGES).put({
        key: mailboxKey(userId, mailAccountId, folder),
        messages,
        uidvalidity,
        cachedAt: Date.now(),
      });
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  } catch {
    // Non-fatal
  }
}

/**
 * Merge new messages into the existing cached list for a folder.
 * Existing messages with the same UID are updated; new ones are prepended.
 *
 * @param {string|number} userId
 * @param {string|number} mailAccountId
 * @param {string}        folder
 * @param {Array}         newMessages
 * @returns {Promise<void>}
 */
export async function mergeMailboxMessages(userId, mailAccountId, folder, newMessages) {
  const existing = await getMailboxMessages(userId, mailAccountId, folder) || [];
  const existingMap = new Map(existing.map((m) => [m.uid, m]));

  for (const msg of newMessages) {
    existingMap.set(msg.uid, msg);
  }

  // Keep sorted: newest UID first
  const merged = Array.from(existingMap.values()).sort(
    (a, b) => parseInt(b.uid, 10) - parseInt(a.uid, 10)
  );

  await setMailboxMessages(userId, mailAccountId, folder, merged);
}

// ─── Mailbox state (UIDVALIDITY + highest UID) ────────────────────────────────

/**
 * Get the stored mailbox sync state.
 *
 * @param {string|number} userId
 * @param {string|number} mailAccountId
 * @param {string}        folder
 * @returns {Promise<{uidvalidity:number, highestUid:number, syncedAt:number}|null>}
 */
export async function getMailboxState(userId, mailAccountId, folder) {
  try {
    const db = await openInboxDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_STATE, 'readonly');
      const req = tx.objectStore(STORE_STATE).get(mailboxKey(userId, mailAccountId, folder));
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

/**
 * Update the stored mailbox sync state.
 *
 * @param {string|number} userId
 * @param {string|number} mailAccountId
 * @param {string}        folder
 * @param {number}        uidvalidity
 * @param {number}        highestUid
 * @returns {Promise<void>}
 */
export async function setMailboxState(userId, mailAccountId, folder, uidvalidity, highestUid) {
  try {
    const db = await openInboxDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_STATE, 'readwrite');
      tx.objectStore(STORE_STATE).put({
        key: mailboxKey(userId, mailAccountId, folder),
        uidvalidity,
        highestUid,
        syncedAt: Date.now(),
      });
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  } catch {
    // Non-fatal
  }
}

// ─── Email bodies ─────────────────────────────────────────────────────────────

/**
 * Get a cached email body by stable UID.
 *
 * @param {string|number} userId
 * @param {string|number} mailAccountId
 * @param {string}        folder
 * @param {string}        uid     - stable message UID
 * @returns {Promise<{html_body:string, text_body:string}|null>}
 */
export async function getEmailBody(userId, mailAccountId, folder, uid) {
  try {
    const db = await openInboxDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_BODIES, 'readonly');
      const req = tx.objectStore(STORE_BODIES).get(bodyKey(userId, mailAccountId, folder, uid));
      req.onsuccess = () => resolve(req.result ? req.result.body : null);
      req.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

/**
 * Store an email body.
 *
 * @param {string|number} userId
 * @param {string|number} mailAccountId
 * @param {string}        folder
 * @param {string}        uid
 * @param {{html_body:string, text_body:string}} body
 * @returns {Promise<void>}
 */
export async function setEmailBody(userId, mailAccountId, folder, uid, body) {
  try {
    const db = await openInboxDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_BODIES, 'readwrite');
      tx.objectStore(STORE_BODIES).put({
        key: bodyKey(userId, mailAccountId, folder, uid),
        body,
        cachedAt: Date.now(),
      });
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  } catch {
    // Non-fatal
  }
}

// ─── Notification deduplication ───────────────────────────────────────────────

/**
 * Get the set of email UIDs that have already triggered a "new email" toast
 * for a given folder.
 *
 * @param {string|number} userId
 * @param {string|number} mailAccountId
 * @param {string}        folder
 * @returns {Promise<Set<string>>}
 */
export async function getNotifiedUids(userId, mailAccountId, folder) {
  try {
    const db = await openInboxDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_NOTIFIED, 'readonly');
      const req = tx.objectStore(STORE_NOTIFIED).get(mailboxKey(userId, mailAccountId, folder));
      req.onsuccess = () => {
        const record = req.result;
        resolve(new Set(record ? record.uids : []));
      };
      req.onerror = () => resolve(new Set());
    });
  } catch {
    return new Set();
  }
}

/**
 * Mark a list of UIDs as having already triggered a notification.
 *
 * @param {string|number} userId
 * @param {string|number} mailAccountId
 * @param {string}        folder
 * @param {string[]}      uids
 * @returns {Promise<void>}
 */
export async function markUidsNotified(userId, mailAccountId, folder, uids) {
  if (!uids || uids.length === 0) return;
  try {
    const existing = await getNotifiedUids(userId, mailAccountId, folder);
    const merged = new Set([...existing, ...uids]);

    const db = await openInboxDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_NOTIFIED, 'readwrite');
      tx.objectStore(STORE_NOTIFIED).put({
        key: mailboxKey(userId, mailAccountId, folder),
        uids: Array.from(merged),
        updatedAt: Date.now(),
      });
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  } catch {
    // Non-fatal
  }
}

// ─── UIDVALIDITY reset ────────────────────────────────────────────────────────

/**
 * Reset all cached data for a specific mailbox folder.
 *
 * Called when the server reports a UIDVALIDITY change, meaning previous UIDs
 * are no longer trustworthy for this folder.
 *
 * Does NOT clear other folders or other resources (market events, prospects, etc.).
 *
 * @param {string|number} userId
 * @param {string|number} mailAccountId
 * @param {string}        folder
 * @returns {Promise<void>}
 */
export async function resetMailboxCache(userId, mailAccountId, folder) {
  const key = mailboxKey(userId, mailAccountId, folder);
  try {
    const db = await openInboxDB();

    // Delete messages
    await new Promise((resolve) => {
      const tx = db.transaction(STORE_MESSAGES, 'readwrite');
      tx.objectStore(STORE_MESSAGES).delete(key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });

    // Delete mailbox state
    await new Promise((resolve) => {
      const tx = db.transaction(STORE_STATE, 'readwrite');
      tx.objectStore(STORE_STATE).delete(key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });

    // Delete bodies for this folder via cursor (key prefix: userId:accountId:folder:)
    const bodyPrefix = `${key}:`;
    await new Promise((resolve) => {
      const tx = db.transaction(STORE_BODIES, 'readwrite');
      const store = tx.objectStore(STORE_BODIES);
      const req = store.openCursor();
      req.onsuccess = (event) => {
        const cursor = event.target.result;
        if (!cursor) return;
        if (cursor.key.startsWith(bodyPrefix)) cursor.delete();
        cursor.continue();
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });

    // Delete notification state
    await new Promise((resolve) => {
      const tx = db.transaction(STORE_NOTIFIED, 'readwrite');
      tx.objectStore(STORE_NOTIFIED).delete(key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  } catch {
    // Non-fatal; caller will rebuild on next fetch
  }
}

// ─── User logout ──────────────────────────────────────────────────────────────

/**
 * Clear ALL inbox-related cached data for a specific user.
 * Called on logout to prevent data leakage to the next user.
 *
 * @param {string|number} userId
 * @returns {Promise<void>}
 */
export async function clearUserInboxCache(userId) {
  if (!userId) return;
  const prefix = String(userId) + ':';
  const stores = [STORE_MESSAGES, STORE_BODIES, STORE_STATE, STORE_NOTIFIED];

  try {
    const db = await openInboxDB();
    for (const storeName of stores) {
      await new Promise((resolve) => {
        const tx = db.transaction(storeName, 'readwrite');
        const store = tx.objectStore(storeName);
        const req = store.openCursor();
        req.onsuccess = (event) => {
          const cursor = event.target.result;
          if (!cursor) return;
          if (cursor.key.startsWith(prefix)) cursor.delete();
          cursor.continue();
        };
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      });
    }
  } catch {
    // Non-fatal
  }
}
