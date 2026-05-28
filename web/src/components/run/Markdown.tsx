import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { t } from '@/i18n';

// Defensive: if the whole content is wrapped in one ```/```markdown fence
// (some translation models do this), unwrap it so it renders as Markdown
// rather than a literal code block. Also drops echoed prompt delimiters.
function unwrap(source: string): string {
  let s = source.trim();
  s = s.replace(/^-{3,}\s*BEGIN REPORT\s*-{3,}\s*/i, '');
  s = s.replace(/\s*-{3,}\s*END REPORT\s*-{3,}\s*$/i, '');
  s = s.trim();
  if (s.startsWith('```')) {
    const lines = s.split('\n');
    lines.shift(); // opening ``` / ```markdown
    if (lines.length && lines[lines.length - 1].trim().startsWith('```')) {
      lines.pop(); // closing ```
    }
    s = lines.join('\n').trim();
  }
  return s;
}

export default function Markdown({ source }: { source: string }) {
  if (!source || !source.trim()) {
    return <div className="text-muted text-sm italic">{t('markdown.empty')}</div>;
  }
  return (
    <div className="prose-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{unwrap(source)}</ReactMarkdown>
    </div>
  );
}
