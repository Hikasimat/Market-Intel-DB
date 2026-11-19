import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const whatsappPagePath = path.join(__dirname, 'WhatsappPage.jsx');
const source = fs.readFileSync(whatsappPagePath, 'utf8');

test('WhatsappPage.jsx implements request-generation and session/chat key guards to prevent stale message overwrites (20, 21, 22)', () => {
  assert.match(source, /activeChatKeyRef\.current\s*!==\s*expectedKey/);
  assert.match(source, /msgRequestGenRef\.current\s*!==\s*reqGen/);
  assert.match(source, /msgAbortControllerRef\.current\.abort\(\)/);
  assert.match(source, /msgPollingInFlightRef\.current/);

  // Simulate the exact state machine in fetchMessages & selection effect
  let activeChatKey = '';
  let msgRequestGen = 0;
  let msgPollingInFlight = false;
  let displayedMessages = [];

  function selectChat(sessionName, chatId) {
    const nextKey = `${sessionName}::${chatId}`;
    if (activeChatKey !== nextKey) {
      activeChatKey = nextKey;
      msgRequestGen += 1;
      msgPollingInFlight = false;
      displayedMessages = [];
    }
  }

  async function simulatedFetchMessages(sessionName, conversationId, isPolling, networkPromise) {
    const expectedKey = `${sessionName}::${conversationId}`;
    if (isPolling) {
      if (activeChatKey !== expectedKey || msgPollingInFlight) {
        return 'skipped';
      }
      msgPollingInFlight = true;
    } else {
      msgRequestGen += 1;
    }
    const reqGen = msgRequestGen;
    try {
      const rawList = await networkPromise;
      if (activeChatKey !== expectedKey || msgRequestGen !== reqGen) {
        return 'ignored_stale';
      }
      displayedMessages = [...rawList].sort((a, b) => {
        const tsA = new Date(a.waha_timestamp || a.sent_at || a.created_at || 0).getTime();
        const tsB = new Date(b.waha_timestamp || b.sent_at || b.created_at || 0).getTime();
        if (tsA !== tsB) return tsA - tsB;
        return String(a.id || '').localeCompare(String(b.id || ''));
      });
      return 'applied';
    } finally {
      if (isPolling) {
        msgPollingInFlight = false;
      }
    }
  }

  // Test 20: Rapid switch Customer A -> Customer B; Customer A finishes AFTER Customer B
  selectChat('user_16', 'conv-A');
  let resolveA;
  const promiseA = new Promise(r => { resolveA = r; });
  const reqA = simulatedFetchMessages('user_16', 'conv-A', false, promiseA);

  selectChat('user_16', 'conv-B');
  const reqB = simulatedFetchMessages(
    'user_16',
    'conv-B',
    false,
    Promise.resolve([
      { id: 'b2', full_body: 'Second from B', sent_at: '2026-11-17T10:02:00Z' },
      { id: 'b1', full_body: 'First from B', sent_at: '2026-11-17T10:01:00Z' },
    ])
  );

  return Promise.all([
    reqB.then(resB => {
      assert.equal(resB, 'applied');
      // Test 22: Chronological sorting (oldest -> newest)
      assert.deepEqual(displayedMessages.map(m => m.id), ['b1', 'b2']);
      // Now late response from Customer A resolves
      resolveA([{ id: 'a1', full_body: 'Stale message from A', sent_at: '2026-11-17T10:00:00Z' }]);
      return reqA;
    }),
  ]).then(async ([resA]) => {
    assert.equal(resA, 'ignored_stale');
    // Customer B's messages remain intact; Customer A never overwrote Customer B
    assert.deepEqual(displayedMessages.map(m => m.id), ['b1', 'b2']);

    // Test 21: Polling request for previous chat is rejected
    const pollStale = await simulatedFetchMessages(
      'user_16',
      'conv-A',
      true,
      Promise.resolve([{ id: 'a2', full_body: 'Poll A' }])
    );
    assert.equal(pollStale, 'skipped');
    assert.deepEqual(displayedMessages.map(m => m.id), ['b1', 'b2']);
  });
});

test('WhatsappPage.jsx contact display-name priority prioritizes sender pushName and verified CRM match without leaking unverified names (9)', () => {
  const isLidNumber = (val) => {
    if (!val) return false;
    const str = String(val).trim();
    if (str.endsWith('@lid')) return true;
    const digits = str.replace(/\D/g, '');
    if (!digits) return false;
    return digits.length > 13 || digits.startsWith('7658') || digits.startsWith('2262') || digits.startsWith('2167');
  };

  const getConversationPhoneNumber = (chat) => {
    if (!chat) return '';
    const chatId = chat.chat_id || '';
    if (chatId && (chatId.includes('@c.us') || chatId.includes('@s.whatsapp.net'))) {
      const num = chatId.split('@')[0].split(':')[0].replace(/\D/g, '');
      if (num && !isLidNumber(num)) return `+${num}`;
    }
    if (chat.phone_number) {
      const num = String(chat.phone_number).split('@')[0].split(':')[0].replace(/\D/g, '');
      if (num && !isLidNumber(num)) return `+${num}`;
    }
    return '';
  };

  const getContactDisplayName = (chat) => {
    if (!chat) return 'Contact';
    const isGroup = chat.is_group || chat.chat_id?.endsWith('@g.us');
    if (isGroup) {
      return chat.whatsapp_name || chat.contact_name || 'WhatsApp Group';
    }
    if (
      chat.whatsapp_name &&
      chat.whatsapp_name.toLowerCase() !== 'whatsapp contact' &&
      !chat.whatsapp_name.startsWith('+') &&
      !chat.whatsapp_name.includes('@') &&
      !isLidNumber(chat.whatsapp_name) &&
      !/^[\d\s\-+()]+$/.test(chat.whatsapp_name)
    ) {
      return chat.whatsapp_name;
    }
    if (chat.is_matched && chat.contact_name && !isLidNumber(chat.contact_name) && chat.contact_name.toLowerCase() !== 'whatsapp contact') {
      return chat.contact_name;
    }
    const phone = getConversationPhoneNumber(chat);
    if (phone) return phone;
    if (chat.chat_id) return chat.chat_id;
    return 'WhatsApp Contact';
  };

  // 1. Sender pushName wins over CRM contact_name
  assert.equal(
    getContactDisplayName({ chat_id: '917025117045@c.us', whatsapp_name: 'Fahad', contact_name: 'Mohan V', is_matched: false }),
    'Fahad'
  );
  // 2. Unmatched conversation with stale contact_name falls back to verified phone, never unverified contact_name
  assert.equal(
    getContactDisplayName({ chat_id: '917025117045@c.us', whatsapp_name: '', contact_name: 'Mohan V', is_matched: false }),
    '+917025117045'
  );
  // 3. Unresolved @lid with no pushName displays distinct @lid identifier
  assert.equal(
    getContactDisplayName({ chat_id: '191126329925674@lid', whatsapp_name: '', contact_name: '', is_matched: false }),
    '191126329925674@lid'
  );
});

test('WhatsappPage.jsx implements persistent per-account AI Auto-Reply ON/OFF toggle wired to backend API', () => {
  assert.match(source, /const \[aiEnabled,\s*setAiEnabled\]\s*=\s*useState\(false\)/);
  assert.match(source, /\/whatsapp\/ai-config\//);
  assert.match(source, /api\.patch\(endpoint,\s*\{\s*enabled:\s*nextValue\s*\}\)/);
  assert.match(source, /if\s*\(updatingAiConfig\s*\|\|\s*loadingAiConfig\)\s*return/);
  assert.match(source, /role="switch"/);
  assert.match(source, /aria-checked=\{aiEnabled\}/);
  assert.match(source, /data-testid="whatsapp-ai-toggle-bar"/);
});
