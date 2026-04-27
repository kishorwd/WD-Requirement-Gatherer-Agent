import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import '../styles/index.css';

export default function MarkdownViewer({ content }) {
  if (!content) return null;
  return (
    <div className="markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
