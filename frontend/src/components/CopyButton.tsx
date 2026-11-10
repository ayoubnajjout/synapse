import { useEffect, useRef, useState } from 'react';
import { Check, Copy } from 'lucide-react';

async function copyText(text: string) {
  try {
    if (navigator.clipboard) { await navigator.clipboard.writeText(text); return; }
  } catch { /* Try text selection on browsers without clipboard permission. */ }
  const focused = document.activeElement as HTMLElement | null;
  const field = document.createElement('textarea');
  field.value = text;
  field.readOnly = true;
  field.style.cssText = 'position:fixed;left:-9999px;top:0';
  document.body.append(field);
  try {
    field.select();
    if (!document.execCommand('copy')) throw new Error('Clipboard unavailable');
  } finally { field.remove(); focused?.focus({ preventScroll: true }); }
}

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'error'>('idle');
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => { setState('idle'); }, [text]);
  return <button className="copy-button" aria-label={label} onClick={async () => {
    clearTimeout(timer.current);
    try { await copyText(text); setState('copied'); }
    catch { setState('error'); }
    timer.current = setTimeout(() => setState('idle'), 2000);
  }}>{state === 'copied' ? <Check size={14}/> : <Copy size={14}/>}<span role="status">{state === 'copied' ? 'Copied' : state === 'error' ? 'Select text to copy' : label}</span></button>;
}
