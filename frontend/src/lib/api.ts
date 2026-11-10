export interface Conversation { id: string; title: string; created_at: string; updated_at: string }
export interface Message { id: string; conversation_id: string; sequence: number; role: 'user' | 'assistant'; content: string; provider: string | null; model: string | null; status: string; created_at: string }
export interface Memory { id: string; content: string; enabled: boolean; created_at: string; updated_at: string }
export interface Provider { id: string; name: string; local: boolean; configured: boolean; key_configured: boolean; api_base: string | null; models: string[]; saved_models: string[]; default_model: string | null }
export interface ModelCatalog { models: string[]; default_model: string | null; source: 'live' | 'cached' | 'saved' | 'unavailable'; warning: string | null; truncated: boolean }
export interface Preferences { memory_enabled: boolean; context_chars: number; max_messages: number; max_output_tokens: number }
export interface Settings { preferences: Preferences; providers: Provider[] }
export interface ContextInfo { included_messages: number; excluded_messages: number; included_memories: number; excluded_memories: number; context_chars: number }
export type StreamEvent = { type: 'delta'; text: string } | { type: 'context'; data: ContextInfo } | { type: 'done'; message: Message };

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const error = await response.json();
      message = typeof error.detail === 'string' ? error.detail : 'Some values are invalid. Check your input and try again.';
    } catch { /* The server may return a non-JSON error. */ }
    throw new Error(message);
  }
  return response.status === 204 ? undefined as T : response.json();
}

export async function generate(id: string, body: object, signal: AbortSignal, onEvent: (event: StreamEvent) => void) {
  const response = await fetch(`/api/conversations/${id}/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : 'Unable to start generation.');
  }
  if (!response.body) throw new Error('Streaming is not available in this browser.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', completed = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n');
      let end: number;
      while ((end = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, end); buffer = buffer.slice(end + 2);
        const type = frame.split('\n').find(line => line.startsWith('event:'))?.slice(6).trim();
        const raw = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
        if (!raw) continue;
        const data = JSON.parse(raw);
        if (type === 'error') throw new Error(data.message);
        if (type === 'delta') onEvent({ type: 'delta', text: data.text });
        if (type === 'context') onEvent({ type: 'context', data });
        if (type === 'done') { completed = true; onEvent({ type: 'done', message: data.message }); }
      }
      if (done) break;
    }
    if (!completed) throw new Error('The connection ended before the response was saved. Please retry.');
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}

export async function download(path: string, filename: string) {
  const data = await api<unknown>(path);
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
