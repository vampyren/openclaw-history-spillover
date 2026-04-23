import fs from 'node:fs';
import path from 'node:path';

export const CHAT_HISTORY_SPILLOVER_DIRNAME = 'history-oversize';
export const CHAT_HISTORY_PREVIEW_MAX_CHARS = 1200;
export const CHAT_HISTORY_SPILLED_MARKER = '[chat.history spilled: message too large]';

export function jsonUtf8Bytes(value) {
  return Buffer.byteLength(JSON.stringify(value), 'utf8');
}

export function safeSerializeForSpillover(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch (err) {
    return JSON.stringify({ error: String(err), fallback: String(value) }, null, 2);
  }
}

export function extractChatHistoryPreview(message, maxChars = CHAT_HISTORY_PREVIEW_MAX_CHARS) {
  try {
    const raw = typeof message === 'string' ? message : safeSerializeForSpillover(message);
    return raw.length > maxChars ? `${raw.slice(0, maxChars)}\n…[truncated preview]` : raw;
  } catch {
    return '[preview unavailable]';
  }
}

export function sanitizeIdPart(value, fallback = 'item') {
  const out = String(value ?? fallback).replace(/[^a-zA-Z0-9._-]+/g, '_');
  return out || fallback;
}

export function ensureChatHistorySpilloverDir(baseDir) {
  const dir = path.join(baseDir, CHAT_HISTORY_SPILLOVER_DIRNAME);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

export function persistOversizedHistoryMessage(message, options = {}) {
  const transcriptPath = options.transcriptPath;
  const baseDir = transcriptPath ? path.dirname(transcriptPath) : path.join(process.cwd(), '.openclaw-history');
  const dir = ensureChatHistorySpilloverDir(baseDir);
  const ts = new Date(options.now ?? Date.now()).toISOString().replace(/[:.]/g, '-');
  const sessionPart = sanitizeIdPart(options.sessionId || 'session', 'session');
  const idPart = sanitizeIdPart(options.messageId || Date.now(), 'message');
  const filePath = path.join(dir, `${ts}-${sessionPart}-${idPart}.json`);
  const payload = {
    createdAt: new Date(options.now ?? Date.now()).toISOString(),
    sessionId: options.sessionId ?? null,
    transcriptPath: transcriptPath ?? null,
    byteLength: jsonUtf8Bytes(message),
    message
  };
  fs.writeFileSync(filePath, safeSerializeForSpillover(payload), 'utf8');
  return filePath;
}

export function buildOversizedHistorySpilloverPlaceholder(message, options = {}) {
  const preview = extractChatHistoryPreview(message, options.previewMaxChars);
  const byteLength = jsonUtf8Bytes(message);
  const filePath = persistOversizedHistoryMessage(message, options);
  return {
    role: message && typeof message === 'object' && typeof message.role === 'string' ? message.role : 'assistant',
    timestamp: message && typeof message === 'object' && typeof message.timestamp === 'number' ? message.timestamp : Date.now(),
    content: [{
      type: 'text',
      text: `${CHAT_HISTORY_SPILLED_MARKER}\nbytes=${byteLength}${filePath ? `\nfile=${filePath}` : ''}\npreview:\n${preview}`
    }],
    __openclaw: {
      truncated: true,
      reason: 'oversized',
      spilloverFile: filePath,
      originalBytes: byteLength
    }
  };
}

export function replaceOversizedChatHistoryMessages({ messages, maxSingleMessageBytes, transcriptPath, sessionId }) {
  if (!Array.isArray(messages) || messages.length === 0) return { messages: messages ?? [], replacedCount: 0 };
  let replacedCount = 0;
  const next = messages.map((message, index) => {
    if (jsonUtf8Bytes(message) <= maxSingleMessageBytes) return message;
    replacedCount += 1;
    return buildOversizedHistorySpilloverPlaceholder(message, { transcriptPath, sessionId, messageId: index });
  });
  return { messages: replacedCount > 0 ? next : messages, replacedCount };
}
