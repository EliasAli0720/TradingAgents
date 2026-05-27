import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { t } from '@/i18n';

export default function Markdown({ source }: { source: string }) {
  if (!source || !source.trim()) {
    return <div className="text-muted text-sm italic">{t('markdown.empty')}</div>;
  }
  return (
    <div className="prose-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{source}</ReactMarkdown>
    </div>
  );
}
