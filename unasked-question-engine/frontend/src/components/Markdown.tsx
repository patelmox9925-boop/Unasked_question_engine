import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";

/** Markdown renderer with HTML sanitisation. Raw HTML and images are never rendered. */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        rehypePlugins={[rehypeSanitize]}
        skipHtml
        disallowedElements={["img"]}
        components={{
          a: ({ href, children: content }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {content}
            </a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
