export function Brand({ small = false }: { small?: boolean }) {
  return <span className={`brand-mark ${small ? 'small' : ''}`} aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="m9 9 14 14M23 9 9 23M9 9h14M9 23h14" stroke="currentColor" strokeWidth="1.5"/><circle cx="9" cy="9" r="3.4" fill="currentColor"/><circle cx="23" cy="9" r="3.4" fill="currentColor"/><circle cx="9" cy="23" r="3.4" fill="currentColor"/><circle cx="23" cy="23" r="3.4" fill="currentColor"/></svg></span>;
}
