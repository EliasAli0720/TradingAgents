import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function Markdown({ source }: { source: string }) {
  if (!source || !source.trim()) {
    return <div className="text-muted text-sm italic">（暂无内容）</div>;
  }
  return (
    <div className="prose-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{source}</ReactMarkdown>
    </div>
  );
}
