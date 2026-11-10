import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, Globe, HardDrive, LoaderCircle, RefreshCw, Search, Settings2, X } from 'lucide-react';
import type { Provider } from '../lib/api';

export function ModelSelector({ providers, value, onChange, onConfigure, onRefresh, loading, disabled }: {
  providers: Provider[]; value: string; onChange: (value: string) => void; onConfigure: () => void;
  onRefresh: () => void; loading: boolean; disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const root = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const selected = providers.find(p => value.startsWith(`${p.id}::`));
  const model = value.slice(value.indexOf('::') + 2);
  const choices = providers.filter(p => p.configured).flatMap(p => p.models.map(id => ({ provider: p, id, key: `${p.id}::${id}` }))).filter(m => `${m.provider.name} ${m.id}`.toLowerCase().includes(query.toLowerCase()));
  useEffect(() => {
    if (!open) return;
    search.current?.focus();
    function close(event: PointerEvent) { if (!root.current?.contains(event.target as Node)) setOpen(false); }
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, [open]);
  function choose(key: string) { onChange(key); setOpen(false); trigger.current?.focus(); }
  function row(choice: typeof choices[number]) {
    const { key, id, provider } = choice;
    return <div className={`model-option ${value === key ? 'selected' : ''}`} key={key}>
      <button className="model-option-pick" onClick={() => choose(key)} aria-label={`Use ${provider.name} / ${id}`}><span className="model-option-icon">{provider.local ? <HardDrive size={16}/> : <Globe size={16}/>}</span><span><strong>{id}</strong><small>{provider.name}</small></span>{value === key && <Check size={16}/>}</button>

    </div>;
  }
  return <div className="model-selector" ref={root} onKeyDown={event => {
    if (event.key === 'Escape') { setOpen(false); trigger.current?.focus(); }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      const buttons = Array.from(root.current?.querySelectorAll<HTMLButtonElement>('.model-option-pick') || []);
      if (!buttons.length) return;
      event.preventDefault(); const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
      buttons[(index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length]?.focus();
    }
  }}>
    <button className="model-trigger" ref={trigger} disabled={disabled} onClick={() => { setOpen(!open); setQuery(''); }} aria-expanded={open} aria-haspopup="dialog" aria-label="Choose model"><span className="provider-symbol">{loading && !value ? <LoaderCircle size={16} className="spin"/> : selected?.local ? <HardDrive size={16}/> : <Globe size={16}/>}</span><span>{value ? model : loading ? 'Finding your models…' : 'Choose a model'}{selected && <small>{selected.name}</small>}</span><ChevronDown size={15}/></button>
    {open && <div className="model-popover" role="dialog" aria-label="Choose a model">
      <div className="model-search"><Search size={16}/><input ref={search} placeholder="Search models or providers…" value={query} onChange={e => setQuery(e.target.value)} aria-label="Search models"/><button className="icon-button" aria-label="Close model chooser" onClick={() => { setOpen(false); trigger.current?.focus(); }}><X size={16}/></button></div>
      <div className="model-options">{providers.filter(p => choices.some(m => m.provider.id === p.id)).map(p => <section key={p.id}><h3>{p.name}</h3>{choices.filter(m => m.provider.id === p.id).map(row)}</section>)}{choices.length === 0 && <div className="model-empty">{loading ? <><LoaderCircle size={20} className="spin"/><span>Loading models…</span></> : <span>{query ? 'No matching models.' : 'Connect a provider to see its models.'}</span>}</div>}</div>
      <div className="model-popover-footer"><button disabled={loading} onClick={onRefresh}><RefreshCw size={14} className={loading ? 'spin' : ''}/>Refresh models</button><button onClick={() => { setOpen(false); onConfigure(); }}><Settings2 size={14}/>Manage providers</button></div>
    </div>}
  </div>;
}
