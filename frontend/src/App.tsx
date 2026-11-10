import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowRight, ArrowUp, BookOpen, Database, Download, Ellipsis, LoaderCircle, Menu, MessageSquare, PanelLeftClose, Pencil, Plus, Search, Settings2, Square, Trash2, X } from 'lucide-react';
import { api, download, generate, type ContextInfo, type ModelCatalog, type Conversation, type Memory, type Message as ChatMessage, type Settings as AppSettings } from './lib/api';
import { Brand } from './components/Brand';
import { ModelSelector } from './components/ModelSelector';
import { Dialog } from './components/Dialog';
import { Message } from './components/Message';
import { Settings, type Tab } from './components/Settings';

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [modelKey, setModelKey] = useState(() => { try { return localStorage.getItem('synapse-selected-model') || ''; } catch { return ''; } });
  const [discovering, setDiscovering] = useState(false);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [booting, setBooting] = useState(true);
  const [atBottom, setAtBottom] = useState(true);
  const [partial, setPartial] = useState<ChatMessage | null>(null);
  const [context, setContext] = useState<ContextInfo | null>(null);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [panel, setPanel] = useState<Tab | null>(null);
  const [mobileSidebar, setMobileSidebar] = useState(false);
  const [search, setSearch] = useState('');
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem('synapse-theme') || 'dark'; } catch { return 'dark'; } });
  const [menu, setMenu] = useState(false);
  const [edit, setEdit] = useState<{ kind: 'rename' | 'delete'; id: string; title: string } | null>(null);
  const [rename, setRename] = useState('');
  const abort = useRef<AbortController | null>(null);
  const catalogVersion = useRef(0);
  const operation = useRef(false);
  const messageRetry = useRef<{ content: string; id: string } | null>(null);
  const generationRetry = useRef<{ conversation: string; provider: string; model: string; regenerate: boolean; id: string } | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const scrollArea = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const composer = useRef<HTMLTextAreaElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const selectedConversation = conversations.find(c => c.id === selected);
  const providerId = modelKey.split('::')[0];
  const modelId = modelKey.slice(providerId.length + 2);
  const provider = settings?.providers.find(p => p.id === providerId);
  const lastMessage = messages.at(-1);
  const pendingUser = lastMessage?.role === 'user';

  async function refreshConversations() { setConversations(await api<Conversation[]>('/conversations')); }
  async function refreshModels(force = false, source: AppSettings | null = settings) {
    if (!source) return;
    const version = ++catalogVersion.current;
    setDiscovering(true);
    const results = await Promise.allSettled(source.providers.map(async p => {
      if (!p.configured) return p;
      const catalog = await api<ModelCatalog>(`/providers/${p.id}/models${force ? '?refresh=true' : ''}`);
      return { ...p, models: catalog.models };
    }));
    if (version !== catalogVersion.current) return;
    const providers = results.map((result, index) => result.status === 'fulfilled' ? result.value : source.providers[index]);
    setSettings(previous => previous ? { ...previous, providers } : previous);
    setModelKey(previous => {
      if (providers.some(p => p.configured && p.models.some(model => `${p.id}::${model}` === previous))) return previous;
      const first = providers.find(p => p.configured && p.models.length);
      return first ? `${first.id}::${first.default_model || first.models[0]}` : '';
    });
    setDiscovering(false);
  }
  async function refreshSettings() {
    const [s, m] = await Promise.all([api<AppSettings>('/settings'), api<Memory[]>('/memories')]);
    setSettings(s); setMemories(m);
    await refreshModels(false, s);
  }
  async function initialize() {
    setBooting(true); setError('');
    try { await Promise.all([refreshConversations(), refreshSettings()]); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBooting(false); }
  }
  useEffect(() => { void initialize(); return () => abort.current?.abort(); }, []);
  useEffect(() => {
    function focusSearch(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (event.key === '/' && !target.closest('input, textarea, select, [contenteditable], dialog')) {
        event.preventDefault(); setMobileSidebar(true); searchInput.current?.focus();
      }
    }
    window.addEventListener('keydown', focusSearch);
    return () => window.removeEventListener('keydown', focusSearch);
  }, []);
  useEffect(() => { if (modelKey) { try { localStorage.setItem('synapse-selected-model', modelKey); } catch { /* Optional storage. */ } } }, [modelKey]);
  useEffect(() => { document.documentElement.dataset.theme = theme; try { localStorage.setItem('synapse-theme', theme); } catch { /* Optional storage. */ } }, [theme]);
  useEffect(() => { if (stickToBottom.current) bottom.current?.scrollIntoView({ behavior: busy ? 'instant' : 'smooth' }); }, [messages, partial, busy]);
  useEffect(() => { if (composer.current) { composer.current.style.height = 'auto'; composer.current.style.height = `${Math.min(composer.current.scrollHeight, 180)}px`; } }, [draft]);

  function errorMessage(e: unknown) { return e instanceof Error ? e.message : 'Something went wrong. Please try again.'; }
  async function openConversation(id: string) {
    if (operation.current) return;
    operation.current = true; setLoading(true); setError(''); setInfo(''); setPartial(null); setContext(null); setMobileSidebar(false); setMenu(false);
    try { const stored = await api<ChatMessage[]>(`/conversations/${id}/messages`); setSelected(id); setMessages(stored); setAtBottom(true); setDraft(''); generationRetry.current = null; stickToBottom.current = true; }
    catch (e) { setError(errorMessage(e)); }
    finally { setLoading(false); operation.current = false; }
  }
  function newChat() {
    if (operation.current) return;
    setSelected(null); setMessages([]); setAtBottom(true); setDraft(''); setPartial(null); setContext(null); setError(''); setInfo(''); setMobileSidebar(false); setMenu(false); generationRetry.current = null; messageRetry.current = null; composer.current?.focus();
  }
  async function runGeneration(id: string, regenerate: boolean) {
    const previous = generationRetry.current;
    const request = previous && previous.conversation === id && previous.provider === providerId && previous.model === modelId && previous.regenerate === regenerate ? previous : { conversation: id, provider: providerId, model: modelId, regenerate, id: crypto.randomUUID() };
    generationRetry.current = request;
    const controller = new AbortController(); abort.current = controller;
    setPartial({ id: request.id, conversation_id: id, sequence: 0, role: 'assistant', content: '', provider: provider?.name || providerId, model: modelId, status: 'generating', created_at: new Date().toISOString() });
    let saved = false;
    try {
      await generate(id, { id: request.id, provider: providerId, model: modelId, regenerate }, controller.signal, event => {
        if (event.type === 'context') setContext(event.data);
        if (event.type === 'delta') setPartial(previous => previous ? { ...previous, content: previous.content + event.text } : previous);
        if (event.type === 'done') {
          saved = true;
          setMessages(previous => {
            const base = regenerate && previous.at(-1)?.role === 'assistant' ? previous.slice(0, -1) : previous;
            return [...base.filter(m => m.id !== event.message.id), event.message];
          });
          setPartial(null); generationRetry.current = null;
        }
      });
    } catch (e) {
      if (controller.signal.aborted) setInfo('Generation stopped. Partial text was not saved.');
      else setError(errorMessage(e));
      setPartial(null);
      // The server may have committed just before a disconnect. Reconcile before retry.
      try { const stored = await api<ChatMessage[]>(`/conversations/${id}/messages`); setMessages(stored); if (stored.some(m => m.id === request.id)) { generationRetry.current = null; saved = true; } } catch { /* Retain the last known history. */ }
    } finally {
      abort.current = null;
      if (saved) setPartial(null);
    }
  }
  async function submit(regenerate = false) {
    if (operation.current) return;
    if (!modelKey) { setPanel('providers'); return; }
    if (!regenerate && !pendingUser && !draft.trim()) return;
    operation.current = true; setBusy(true); setError(''); setInfo(''); setMenu(false); stickToBottom.current = true;
    let id = selected;
    try {
      if (!id) {
        const created = await api<Conversation>('/conversations', { method: 'POST', body: '{}' });
        id = created.id; setSelected(id); setConversations(previous => [created, ...previous]);
      }
      if (!regenerate && !pendingUser) {
        const content = draft.trim();
        if (!messageRetry.current || messageRetry.current.content !== content) messageRetry.current = { id: crypto.randomUUID(), content };
        const message = await api<ChatMessage>(`/conversations/${id}/messages`, { method: 'POST', body: JSON.stringify(messageRetry.current) });
        setMessages(previous => [...previous.filter(m => m.id !== message.id), message]);
        setDraft(''); messageRetry.current = null; generationRetry.current = null;
      }
      await runGeneration(id, regenerate);
      await refreshConversations();
    } catch (e) { setError(errorMessage(e)); }
    finally { operation.current = false; setBusy(false); composer.current?.focus(); }
  }
  async function editConversation() {
    if (!edit) return;
    try {
      await api(`/conversations/${edit.id}`, { method: edit.kind === 'delete' ? 'DELETE' : 'PATCH', ...(edit.kind === 'rename' ? { body: JSON.stringify({ title: rename }) } : {}) });
      if (edit.kind === 'delete' && selected === edit.id) newChat();
      setEdit(null); await refreshConversations();
    } catch (e) { setError(errorMessage(e)); setEdit(null); }
  }
  function showEdit(kind: 'rename' | 'delete', c: Conversation) { setEdit({ kind, id: c.id, title: c.title }); setRename(c.title); setMenu(false); }
  const filtered = conversations.filter(c => c.title.toLowerCase().includes(search.toLowerCase()));
  const today = new Date().toDateString();
  const groups = [
    { label: 'Today', items: filtered.filter(c => new Date(c.updated_at).toDateString() === today) },
    { label: 'Earlier', items: filtered.filter(c => new Date(c.updated_at).toDateString() !== today) },
  ];

  return <div className={`workspace ${!messages.length && !partial ? 'is-home' : ''}`}>
    {mobileSidebar && <button className="sidebar-overlay" aria-label="Close sidebar" onClick={() => setMobileSidebar(false)}/>}
    <aside className={`sidebar ${mobileSidebar ? 'open' : ''}`}>
      <div className="sidebar-brand"><a href="/" onClick={e => { e.preventDefault(); newChat(); }} aria-label="Synapse home"><Brand/><span>synapse<span className="brand-period">.</span></span></a><button className="icon-button mobile-close" aria-label="Close sidebar" onClick={() => setMobileSidebar(false)}><PanelLeftClose size={18}/></button></div>
      <button className="new-chat button" disabled={busy || loading} onClick={newChat}><Plus size={18}/><span>New chat</span></button>
      <label className="conversation-search"><Search size={15}/><input ref={searchInput} value={search} onChange={e => setSearch(e.target.value)} placeholder="Search conversations" aria-label="Search conversations"/><span>/</span></label>
      <div className="conversation-list">
        {booting && <div className="sidebar-empty"><LoaderCircle size={18} className="spin"/><span>Loading your workspace…</span></div>}
        {!booting && !filtered.length && <div className="sidebar-empty"><MessageSquare size={23}/><span>{search ? 'No conversations found' : 'No chats yet'}</span><small>{search ? 'Try a different search.' : 'Start a chat to see it here.'}</small></div>}
        {groups.map(group => group.items.length > 0 && <div className="conversation-group" key={group.label}><h2>{group.label}</h2>{group.items.map(c => <div className={`conversation-item ${c.id === selected ? 'active' : ''}`} key={c.id}><button className="conversation-open" disabled={busy || loading} onClick={() => openConversation(c.id)}><MessageSquare size={15}/><span>{c.title}</span></button><button className="conversation-rename icon-button" aria-label={`Rename ${c.title}`} disabled={busy || loading} onClick={() => showEdit('rename', c)}><Pencil size={13}/></button></div>)}</div>)}
      </div>
      <div className="sidebar-bottom"><button disabled={busy || !settings} onClick={() => setPanel('providers')}><Settings2 size={17}/>Settings</button></div>
    </aside>
    <main className="main">
      <header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" aria-label="Open sidebar" onClick={() => setMobileSidebar(true)}><Menu size={20}/></button><span className="current-title">{selectedConversation?.title || 'New chat'}</span></div><div className="topbar-right"><ModelSelector providers={settings?.providers || []} value={modelKey} disabled={busy || !settings} loading={discovering} onChange={value => { setModelKey(value); setContext(null); }} onConfigure={() => setPanel('providers')} onRefresh={() => { void refreshModels(true); }}/>{selectedConversation && <div className="conversation-menu"><button className="icon-button" disabled={busy || loading} aria-label="Conversation options" aria-expanded={menu} onClick={() => setMenu(!menu)}><Ellipsis size={20}/></button>{menu && <><button className="menu-dismiss" aria-label="Close conversation options" onClick={() => setMenu(false)}/><div className="dropdown-menu"><button onClick={() => showEdit('rename', selectedConversation)}><Pencil size={15}/>Rename</button><button onClick={async () => { setMenu(false); try { await download(`/conversations/${selected}/export`, 'synapse-conversation.json'); } catch (e) { setError(errorMessage(e)); } }}><Download size={15}/>Export JSON</button><button className="danger" onClick={() => showEdit('delete', selectedConversation)}><Trash2 size={15}/>Delete conversation</button></div></>}</div>}</div></header>
      <div className={`chat-scroll ${messages.length ? 'has-messages' : ''}`} ref={scrollArea} onScroll={() => { const el = scrollArea.current; if (el) { const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120; stickToBottom.current = nearBottom; setAtBottom(nearBottom); } }}>
        {!messages.length && !partial && !loading && <div className="welcome">
          <h1>Start a conversation</h1>
          <p>{modelKey ? 'Choose a model above and send a message.' : 'Connect a provider to choose a model.'}</p>
          {!booting && !modelKey && <button className="button primary setup-hint" disabled={!settings} onClick={() => setPanel('providers')}>Connect a provider</button>}
        </div>}
        {loading && <div className="chat-loading"><LoaderCircle className="spin" size={22}/><span>Opening conversation…</span></div>}
        {messages.length > 0 && <div className="messages">{messages.map((m, i) => <Message message={m} key={m.id} onRetry={i === messages.length - 1 && m.role === 'assistant' && !busy ? () => submit(true) : undefined}/>)}</div>}
        {partial && <div className="messages streaming-message"><Message message={partial} streaming/></div>}
        <div ref={bottom}/>
      </div>
      <div className="composer-region">
        {messages.length > 0 && !atBottom && <button className="jump-latest" onClick={() => { stickToBottom.current = true; setAtBottom(true); bottom.current?.scrollIntoView({ behavior: 'smooth' }); }}><ArrowDown size={14}/>Jump to latest</button>}
        {context && (context.excluded_messages > 0 || context.excluded_memories > 0) && <div className="context-warning" role="status"><BookOpen size={14}/><span>Context includes {context.included_messages} recent messages and {context.included_memories} memories. {context.excluded_messages} older messages and {context.excluded_memories} memories excluded by your limits.</span></div>}
        {error && <div className="chat-alert alert error" role="alert"><span>{error}</span>{!settings && <button className="text-button" onClick={initialize}>Reconnect</button>}<button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><X size={15}/></button></div>}
        {info && <div className="chat-alert alert" role="status"><span>{info}</span><button className="icon-button" aria-label="Dismiss message" onClick={() => setInfo('')}><X size={15}/></button></div>}
        {pendingUser && !busy && <div className="pending-message"><span>Your message is saved. Choose a model and continue.</span><button className="text-button" onClick={() => submit()}>Generate response <ArrowRight size={13}/></button></div>}
        <form className={`composer ${busy ? 'generating' : ''}`} onSubmit={e => { e.preventDefault(); submit(); }}>
          <textarea ref={composer} rows={1} value={draft} maxLength={100000} disabled={busy || loading || !!pendingUser} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (!busy) submit(); } }} placeholder={busy ? 'Writing a response…' : pendingUser ? 'Generate a response to continue this conversation' : 'Ask anything…'} aria-label="Your message"/>
          <div className="composer-bottom"><button type="button" className={`composer-memory ${settings?.preferences.memory_enabled ? 'enabled' : ''}`} disabled={busy || !settings} onClick={() => setPanel('memory')}><Database size={14}/><span>Memory {settings?.preferences.memory_enabled ? 'on' : 'off'}</span></button><div className="send-actions"><span className="enter-hint">{busy ? 'Generating…' : '↵ to send'}</span>{busy ? <button type="button" className="send-button stop" aria-label="Stop generation" onClick={() => abort.current?.abort()}><Square size={13} fill="currentColor"/><span>Stop</span></button> : <button type="submit" className="send-button" aria-label={modelKey ? 'Send message' : 'Configure a provider'} disabled={loading || booting || (!draft.trim() && !pendingUser)}><ArrowUp size={17}/><span>Send</span></button>}</div></div>
        </form>

      </div>
    </main>
    {panel && settings && <Settings key={panel} initialTab={panel} settings={settings} memories={memories} theme={theme} onTheme={setTheme} onUpdate={refreshSettings} onImport={refreshConversations} onChooseModel={value => { setModelKey(value); setContext(null); }} onClose={() => setPanel(null)}/>}
    {edit && <Dialog title={edit.kind === 'rename' ? 'Rename conversation' : 'Delete conversation?'} onClose={() => setEdit(null)}><form className="edit-form" onSubmit={e => { e.preventDefault(); editConversation(); }}>{edit.kind === 'rename' ? <label className="field">Conversation title<input value={rename} onChange={e => setRename(e.target.value)} maxLength={200} required autoFocus/></label> : <p>“{edit.title}” and all its messages will be permanently deleted.</p>}<div className="settings-actions"><button type="button" className="button secondary" onClick={() => setEdit(null)}>Cancel</button><button className={`button ${edit.kind === 'delete' ? 'danger-button' : 'primary'}`} disabled={edit.kind === 'rename' && !rename.trim()}>{edit.kind === 'delete' ? 'Delete conversation' : 'Save title'}</button></div></form></Dialog>}
  </div>;
}
