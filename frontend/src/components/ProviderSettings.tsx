import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, Globe, HardDrive, KeyRound, LoaderCircle, RefreshCw, Search } from 'lucide-react';
import { api, type ModelCatalog, type Provider } from '../lib/api';

export function ProviderSettings({ providers, onUpdate, onChoose }: { providers: Provider[]; onUpdate: () => Promise<void>; onChoose: (key: string) => void }) {
  const [provider, setProvider] = useState(providers.find(p => p.configured)?.id || 'ollama');
  const [drafts, setDrafts] = useState<Record<string, Provider>>(() => Object.fromEntries(providers.map(p => [p.id, p])));
  const [catalogs, setCatalogs] = useState<Record<string, ModelCatalog>>({});
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [custom, setCustom] = useState('');
  const request = useRef(0);
  const current = drafts[provider];
  const catalog = catalogs[provider];
  const models = Array.from(new Set([...(catalog?.models || current.models), ...current.saved_models, ...(current.default_model ? [current.default_model] : [])]));
  const filtered = models.filter(m => m.toLowerCase().includes(query.toLowerCase()));
  const keyVariable = `${provider.toUpperCase()}_API_KEY`;

  function change(patch: Partial<Provider>) { setDrafts(previous => ({ ...previous, [provider]: { ...previous[provider], ...patch } })); setNotice(''); }
  async function load(name: string, refresh = false) {
    const version = ++request.current;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await api<ModelCatalog>(`/providers/${name}/models${refresh ? '?refresh=true' : ''}`);
      if (version !== request.current) return;
      setCatalogs(previous => ({ ...previous, [name]: result }));
      setDrafts(previous => ({ ...previous, [name]: { ...previous[name], default_model: previous[name].default_model || result.default_model || result.models[0] || null } }));
    } catch (e) { if (version === request.current) setError(e instanceof Error ? e.message : 'Could not load models. Try again.'); }
    finally { if (version === request.current) setBusy(false); }
  }
  useEffect(() => {
    setQuery(''); setCustom('');
    void load(provider);
    return () => { request.current++; };
  }, [provider]);

  async function save(connect = false, customModel?: string) {
    setBusy(true); setError(''); setNotice('');
    try {
      const selected = customModel || current.default_model;
      // Store choices/custom IDs, not a frozen copy of a provider's entire catalog.
      const saved = Array.from(new Set([...(selected ? [selected] : []), ...current.saved_models]));
      if (saved.length > 100) throw new Error('This provider already has 100 saved model choices. Your existing choices have been kept. You can still pick any discovered model from the chat menu.');
      await api('/settings', { method: 'PATCH', body: JSON.stringify({ providers: { [provider]: { api_base: current.api_base || null, models: saved, default_model: selected } } }) });
      change({ saved_models: saved, default_model: selected });
      if (connect) await load(provider, true);
      else { setNotice('Model saved. You’re ready to chat.'); setCustom(''); if (selected) onChoose(`${provider}::${selected}`); }
      await onUpdate();
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not save provider.'); }
    finally { setBusy(false); }
  }

  return <div className="provider-settings">
    <div className="section-intro"><h3>Providers</h3><p>Connect a provider, then choose a model.</p></div>
    <div className="provider-tabs">{providers.map(p => <button key={p.id} className={p.id === provider ? 'selected' : ''} disabled={busy} onClick={() => setProvider(p.id)}><span className={`status-dot ${p.configured ? 'ready' : ''}`}/>{p.name}</button>)}</div>
    <div className="provider-heading"><h4>{current.name}</h4><span className="pill">{current.local ? <HardDrive size={13}/> : <Globe size={13}/>} {current.local ? 'On your server' : 'Cloud'}</span></div>
    {!current.local && <div className="info-box">{current.key_configured ? <Check size={17}/> : <KeyRound size={17}/>}<span>{current.key_configured ? 'API key connected. Your available models load automatically.' : <>Add <code>{keyVariable}</code> to your <code>.env</code> file, then run:<code className="setup-command">docker compose up -d --force-recreate backend</code></>}</span></div>}
    {current.local && <label className="field">Server address<input type="url" value={current.api_base || ''} placeholder={provider === 'ollama' ? 'http://localhost:11434' : 'http://localhost:1234'} onChange={e => change({ api_base: e.target.value })}/><small>Use your {current.name} server address. Synapse handles localhost automatically when running in Docker.</small></label>}
    {current.local && <button className="button secondary connect-button" disabled={busy || !current.api_base} onClick={() => save(true)}>{busy ? <LoaderCircle size={15} className="spin"/> : <RefreshCw size={15}/>}Connect & find models</button>}
    {current.local && <div className="info-box"><HardDrive size={16}/><span>{provider === 'ollama' ? 'Automatic hardware: Ollama uses available GPU capacity and falls back to CPU. Synapse retries on CPU if GPU initialization fails before a response starts.' : 'Hardware is managed by LM Studio. Use Auto GPU offload in its model load settings for automatic GPU/CPU placement. Models already loaded keep their existing settings.'}</span></div>}
    <div className="catalog-heading"><div><h4>{current.local ? 'Installed chat models' : 'Available models'}</h4><span>{busy ? 'Finding models…' : `${models.length} ${models.length === 1 ? 'model' : 'models'} · ${catalog?.source === 'live' ? 'up to date' : catalog?.source === 'cached' ? 'recently updated' : 'saved choices'}`}</span></div><button className="icon-button" title="Refresh available models" aria-label="Refresh available models" disabled={busy} onClick={() => load(provider, true)}><RefreshCw size={16} className={busy ? 'spin' : ''}/></button></div>
    {models.length > 5 && <label className="catalog-search"><Search size={16}/><input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Find a model…" aria-label="Find an available model"/></label>}
    <div className="catalog-list" role="radiogroup" aria-label="Default model">
      {busy && !models.length ? <div className="catalog-empty"><LoaderCircle size={22} className="spin"/><p>Getting your models…</p></div> : filtered.length ? filtered.map(model => <label className={`catalog-model ${current.default_model === model ? 'selected' : ''}`} key={model}><input type="radio" name="default-model" value={model} checked={current.default_model === model} onChange={() => change({ default_model: model })}/><span>{model}</span>{current.default_model === model && <span className="catalog-selected">Selected</span>}</label>) : <div className="catalog-empty"><Globe size={24}/><strong>{query ? 'No models match your search' : 'Your models will appear here'}</strong><p>{query ? 'Try another name.' : current.local ? 'Connect your server and make sure a chat model is installed.' : 'Connect your API key to browse available models.'}</p></div>}
    </div>
    {catalog?.warning && <p className="catalog-warning" role="status">{catalog.warning}</p>}{catalog?.truncated && <p className="catalog-warning">Showing the first 1,000 models. You can still add another model in Advanced.</p>}
    <div className="settings-actions"><button className="button primary" disabled={busy || !current.default_model} onClick={() => save()}><Check size={16}/>Save model</button></div>
    <details className="advanced-settings"><summary>Advanced options<ChevronDown size={14}/></summary><p>For custom gateways or models that aren’t listed yet.</p>{!current.local && <label className="field">Custom API endpoint<input type="url" value={current.api_base || ''} placeholder="Use the provider’s default address" onChange={e => change({ api_base: e.target.value })}/><button className="button secondary" disabled={busy} onClick={() => save(true)}>Save endpoint & refresh</button></label>}<form onSubmit={e => { e.preventDefault(); void save(false, custom.trim()); }}><label className="field">Custom model ID<input value={custom} maxLength={200} onChange={e => setCustom(e.target.value)} placeholder="Only if your model is missing"/></label><button className="button secondary" disabled={busy || !custom.trim()}>Add custom model</button></form></details>
    {error && <div className="alert error" role="alert">{error}</div>}{notice && <div className="alert success" role="status"><Check size={16}/>{notice}</div>}
  </div>;
}
