import ReactMarkdown, { type Components } from 'react-markdown';
import { LoaderCircle, RotateCcw, User } from 'lucide-react';
import { Brand } from './Brand';
import { CodeBlock } from './CodeBlock';
import { CopyButton } from './CopyButton';
import type { Message as ChatMessage } from '../lib/api';

// Stable renderer identities preserve code wrapping/copy feedback while scrolling
// or updating other chat controls.
const markdownComponents: Components = {
  pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
  img: ({ alt }) => <span>[Image: {alt}]</span>,
  a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
};

export function Message({ message, streaming, onRetry }: { message: ChatMessage; streaming?: boolean; onRetry?: () => void }) {
  const provider = ({ openai: 'OpenAI', anthropic: 'Claude', gemini: 'Gemini', xai: 'Grok', ollama: 'Ollama', lmstudio: 'LM Studio' } as Record<string, string>)[message.provider || ''] || message.provider || 'Synapse';
  return <article className={`message ${message.role}`}>
    <div className="message-avatar">{message.role === 'user' ? <User size={17}/> : <Brand small/>}</div>
    <div className="message-body">
      <div className="message-heading"><strong>{message.role === 'user' ? 'You' : provider}</strong>{message.role === 'assistant' && <span className="model-label">{message.model}</span>}{streaming && <span className="stream-status" role="status"><LoaderCircle size={12} className="spin"/>Generating…</span>}</div>
      <div className="markdown">{message.role === 'assistant' ? <ReactMarkdown skipHtml components={markdownComponents}>{message.content}</ReactMarkdown> : <p className="user-content">{message.content}</p>}{streaming && !message.content && <span className="typing"><i/><i/><i/></span>}</div>
      {!streaming && <div className="message-actions"><CopyButton text={message.content} label={message.role === 'assistant' ? 'Copy response' : 'Copy message'}/>{onRetry && <button className="message-retry" onClick={onRetry} aria-label="Regenerate response"><RotateCcw size={14}/>Regenerate</button>}</div>}
    </div>
  </article>;
}
