import { isValidElement, useState, type ReactNode } from 'react';
import { WrapText } from 'lucide-react';
import { CopyButton } from './CopyButton';

export function CodeBlock({ children }: { children?: ReactNode }) {
  const [wrap, setWrap] = useState(false);
  const code = isValidElement<{ children?: ReactNode; className?: string }>(children) ? children : null;
  const text = typeof code?.props.children === 'string' ? code.props.children : '';
  const language = /language-([\w+-]+)/.exec(code?.props.className || '')?.[1] || 'code';
  return <div className={`code-block ${wrap ? 'wrapped' : ''}`}>
    <div className="code-toolbar"><span className="code-language">{language}</span><div><button className="code-wrap" onClick={() => setWrap(!wrap)} aria-label="Wrap code" aria-pressed={wrap} title="Wrap long lines"><WrapText size={15}/></button><CopyButton text={text} label="Copy code"/></div></div>
    <pre>{children}</pre>
  </div>;
}
