import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  CHAT_HISTORY_SPILLED_MARKER,
  CHAT_HISTORY_SPILLOVER_DIRNAME,
  buildOversizedHistorySpilloverPlaceholder,
  extractChatHistoryPreview,
  replaceOversizedChatHistoryMessages,
  safeSerializeForSpillover
} from '../src/spillover.js';

test('safeSerializeForSpillover serializes basic values', () => {
  const out = safeSerializeForSpillover({ a: 1 });
  assert.match(out, /"a": 1/);
});

test('extractChatHistoryPreview truncates long content', () => {
  const out = extractChatHistoryPreview('x'.repeat(30), 10);
  assert.equal(out, 'xxxxxxxxxx\n…[truncated preview]');
});

test('buildOversizedHistorySpilloverPlaceholder writes spillover file', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'spillover-'));
  const transcriptPath = path.join(tmp, 'session.jsonl');
  fs.writeFileSync(transcriptPath, '');
  const message = { role: 'assistant', timestamp: 123, content: [{ type: 'text', text: 'x'.repeat(5000) }] };
  const placeholder = buildOversizedHistorySpilloverPlaceholder(message, {
    transcriptPath,
    sessionId: 'agent:main:main',
    messageId: '42',
    now: Date.UTC(2026, 3, 23, 15, 0, 0)
  });
  assert.equal(placeholder.role, 'assistant');
  assert.equal(placeholder.timestamp, 123);
  assert.match(placeholder.content[0].text, /\[chat\.history spilled: message too large\]/);
  assert.ok(placeholder.__openclaw.spilloverFile);
  assert.ok(fs.existsSync(placeholder.__openclaw.spilloverFile));
  assert.match(placeholder.__openclaw.spilloverFile, new RegExp(`${CHAT_HISTORY_SPILLOVER_DIRNAME}.+42\\.json$`));
  const payload = JSON.parse(fs.readFileSync(placeholder.__openclaw.spilloverFile, 'utf8'));
  assert.equal(payload.sessionId, 'agent:main:main');
  assert.equal(payload.byteLength > 0, true);
});

test('replaceOversizedChatHistoryMessages only replaces oversized items', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'spillover-'));
  const transcriptPath = path.join(tmp, 'session.jsonl');
  fs.writeFileSync(transcriptPath, '');
  const small = { role: 'assistant', content: [{ type: 'text', text: 'ok' }] };
  const big = { role: 'assistant', content: [{ type: 'text', text: 'z'.repeat(6000) }] };
  const res = replaceOversizedChatHistoryMessages({
    messages: [small, big],
    maxSingleMessageBytes: 200,
    transcriptPath,
    sessionId: 'abc'
  });
  assert.equal(res.replacedCount, 1);
  assert.equal(res.messages[0], small);
  assert.match(res.messages[1].content[0].text, new RegExp(CHAT_HISTORY_SPILLED_MARKER.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});
