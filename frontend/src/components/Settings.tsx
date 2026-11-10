import { useEffect, useState } from 'react';
import { Check, ChevronDown, Database, Download, Globe, LoaderCircle, Moon, Plus, Save, Settings2, Sun, Trash2, Upload, X } from 'lucide-react';
import { api, download, type Memory, type Settings as AppSettings } from '../lib/api';
import { Dialog } from './Dialog';
import { ProviderSettings } from './ProviderSettings';

export type Tab = 'providers' | 'memory' | 'preferences';
export function Settings({ initialTab, settings, memories, theme, onTheme, onUpdate, onImport, onClose, onChooseModel }: {
  initialTab: Tab; settings: AppSettings; memories: Memory[]; theme: string;
  onTheme: (theme: string) => void; onUpdate: () => Promise<void>; onImport: () => Promise<void>; onClose: () => void; onChooseModel: (key: string) => void;
}) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [working, setWorking] = useState(false);
  const [prefs, setPrefs] = useState(settings.preferences);
  const [memoryText, setMemoryText] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [deleteMemory, setDeleteMemory] = useState<string | null>(null);
  const [memoryEnabled, setMemoryEnabled] = useState(settings.preferences.memory_enabled);
  const [memoryToggles, setMemoryToggles] = useState<Record<string, boolean>>({});
  useEffect(() => setMemoryEnabled(settings.preferences.memory_enabled), [settings.preferences.memory_enabled]);
  useEffect(() => setMemoryToggles({}), [memories]);

  function toggleGlobalMemory(enabled: boolean) {
    setMemoryEnabled(enabled);
    void run(async () => {
      try { await api('/settings', { method: 'PATCH', body: JSON.stringify({ preferences: { ...settings.preferences, memory_enabled: enabled } }) }); }
      catch (error) { setMemoryEnabled(!enabled); throw error; }
    });
  }

  function toggleMemory(id: string, enabled: boolean) {
    setMemoryToggles(previous => ({ ...previous, [id]: enabled }));
    void run(async () => {
      try { await api(`/memories/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled }) }); }
      catch (error) { setMemoryToggles(previous => ({ ...previous, [id]: !enabled })); throw error; }
    });
  }

  async function run(action: () => Promise<void>, success = '') {
    setWorking(true); setError(''); setNotice('');
    try { await action(); await onUpdate(); setNotice(success); }
    catch (error) { setError(error instanceof Error ? error.message : 'Something went wrong.'); }
    finally { setWorking(false); }
  }

  return <Dialog title="Settings" wide onClose={onClose}>
    <div className="settings-tabs" role="tablist" aria-label="Workspace settings">{([
      ['providers', Globe, 'Providers'], ['memory', Database, 'Memory'], ['preferences', Settings2, 'General'],
    ] as const).map(([id, Icon, label]) => <button role="tab" aria-selected={tab === id} key={id} className={tab === id ? 'active' : ''} onClick={() => { setTab(id); setError(''); setNotice(''); }}><Icon size={16}/>{label}</button>)}</div>
    <div className="settings-content">
      {tab === 'providers' && <ProviderSettings providers={settings.providers} onUpdate={onUpdate} onChoose={onChooseModel}/>}
      {tab === 'memory' && <>
        <div className="section-intro"><h3>Shared memory</h3><p>These saved preferences apply to every chat. Each chat keeps its own message history.</p></div>
        <label className="toggle-row"><span><strong>Shared memory</strong><small>Include enabled memories in future requests.</small></span><input type="checkbox" className="switch" checked={memoryEnabled} disabled={working} onChange={e => toggleGlobalMemory(e.target.checked)}/></label>
        <form onSubmit={e => { e.preventDefault(); run(async () => { await api(editing ? `/memories/${editing}` : '/memories', { method: editing ? 'PATCH' : 'POST', body: JSON.stringify({ content: memoryText }) }); setMemoryText(''); setEditing(null); }, editing ? 'Memory updated.' : 'Memory saved.'); }}>
          <label className="field">{editing ? 'Edit memory' : 'Add a memory'}<textarea rows={3} maxLength={4000} value={memoryText} onChange={e => setMemoryText(e.target.value)} placeholder="e.g. I prefer Python, PostgreSQL, and concise explanations." required/></label><div className="settings-actions">{editing && <button type="button" className="button secondary" onClick={() => { setEditing(null); setMemoryText(''); }}>Cancel</button>}<button className="button primary" disabled={working || !memoryText.trim()}><Plus size={15}/>{editing ? 'Update memory' : 'Save memory'}</button></div>
        </form>
        <div className="list-heading"><span>{memories.length} saved {memories.length === 1 ? 'memory' : 'memories'}</span>{memories.length > 0 && <button className="text-button danger" disabled={working} onClick={() => setConfirmClear(true)}>Clear all</button>}</div>
        {confirmClear && <div className="confirm-row"><span>Permanently delete every saved memory?</span><button className="button danger-button" disabled={working} onClick={() => run(async () => { await api('/memories', { method: 'DELETE' }); setConfirmClear(false); }, 'Memories cleared.')}>Delete all</button><button className="icon-button" aria-label="Cancel clearing memories" onClick={() => setConfirmClear(false)}><X size={16}/></button></div>}
        {!memories.length && <div className="empty-memory"><Database size={26}/><p>Your memory starts here.</p><small>Only what you explicitly save is remembered.</small></div>}
        <div className="memory-list">{memories.map(m => <div key={m.id} className={`memory-row ${!m.enabled ? 'disabled' : ''}`}><input type="checkbox" className="switch" aria-label="Include this memory" checked={memoryToggles[m.id] ?? m.enabled} disabled={working} onChange={e => toggleMemory(m.id, e.target.checked)}/><button className="memory-content" onClick={() => { setEditing(m.id); setMemoryText(m.content); }}>{m.content}</button>{deleteMemory === m.id ? <><button className="text-button danger" disabled={working} onClick={() => run(async () => { await api(`/memories/${m.id}`, { method: 'DELETE' }); setDeleteMemory(null); })}>Confirm delete</button><button className="icon-button" aria-label="Cancel deletion" onClick={() => setDeleteMemory(null)}><X size={15}/></button></> : <button className="icon-button" aria-label="Delete memory" disabled={working} onClick={() => setDeleteMemory(m.id)}><Trash2 size={15}/></button>}</div>)}</div>
        <div className="info-box"><Database size={16}/><span>Memory is explicit and stored in your database. Enabled memories may be sent to your selected provider.</span></div>
      </>}
      {tab === 'preferences' && <>
        <div className="section-intro"><h3>General</h3></div>
        <div className="preference-row"><span><strong>Appearance</strong><small>A comfortable place to think.</small></span><div className="segmented"><button className={theme === 'light' ? 'selected' : ''} onClick={() => onTheme('light')}><Sun size={15}/>Light</button><button className={theme === 'dark' ? 'selected' : ''} onClick={() => onTheme('dark')}><Moon size={15}/>Dark</button></div></div>
        <details className="advanced-settings"><summary>Context limits<ChevronDown size={14}/></summary><h4 className="subheading">Context & generation</h4><p className="small-text">Newest complete messages are included first. Older messages are excluded when either limit is reached; they remain in your history. Memories use up to 25% of the character budget.</p>
        <form onSubmit={e => { e.preventDefault(); run(async () => { await api('/settings', { method: 'PATCH', body: JSON.stringify({ preferences: { ...prefs, memory_enabled: settings.preferences.memory_enabled } }) }); }, 'Preferences saved.'); }}>
          <div className="field-grid"><label className="field">Context budget (characters)<input type="number" min={2000} max={200000} required value={prefs.context_chars} onChange={e => setPrefs({ ...prefs, context_chars: Number(e.target.value) })}/></label><label className="field">Recent message limit<input type="number" min={2} max={200} required value={prefs.max_messages} onChange={e => setPrefs({ ...prefs, max_messages: Number(e.target.value) })}/></label></div><label className="field">Maximum output tokens<input type="number" min={128} max={32768} required value={prefs.max_output_tokens} onChange={e => setPrefs({ ...prefs, max_output_tokens: Number(e.target.value) })}/><small>Choose limits within your selected model's capacity. Character limits approximate token usage.</small></label><div className="settings-actions"><button className="button primary" disabled={working}><Save size={15}/>Save preferences</button></div>
        </form>
        </details><h4 className="subheading">Import / export</h4><div className="data-actions"><button className="button secondary" disabled={working} onClick={() => run(async () => download('/conversations/export', 'synapse-conversations.json'), 'Export downloaded.')}><Download size={16}/>Export all conversations</button><label className={`button secondary file-button ${working ? 'disabled' : ''}`}><Upload size={16}/>Import conversations<input type="file" accept=".json,application/json" disabled={working} onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (!file) return; run(async () => { if (file.size > 10 * 1024 * 1024) throw new Error('Import must be smaller than 10 MiB.'); let data; try { data = JSON.parse(await file.text()); } catch { throw new Error('Choose a valid Synapse JSON export.'); } await api('/conversations/import', { method: 'POST', body: JSON.stringify(data) }); await onImport(); }, 'Conversations imported as new copies.'); }}/></label></div>
      </>}
      {error && <div className="alert error" role="alert">{error}</div>}{notice && <div className="alert success" role="status"><Check size={16}/>{notice}</div>}
      {working && <div className="working-status" role="status"><LoaderCircle size={14} className="spin"/>Working…</div>}
    </div>

  </Dialog>;
}
