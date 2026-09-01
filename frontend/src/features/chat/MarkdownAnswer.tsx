import { Check, Copy } from "lucide-react";
import { Children, isValidElement, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

function textContent(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textContent).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return textContent(node.props.children);
  return "";
}

function CodeFrame({ children }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const code = textContent(children).replace(/\n$/, "");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="code-frame">
      <button type="button" onClick={() => void copy()} aria-label="复制代码">
        {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        {copied ? "已复制" : "复制"}
      </button>
      <pre>{children}</pre>
    </div>
  );
}

export function MarkdownAnswer({
  children,
  onCitation,
}: {
  children: string;
  onCitation: (index: number) => void;
}) {
  return (
    <div className="markdown-answer">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          a: ({ href, children: linkChildren, ...props }) => {
            const citation = /^#cite-(\d+)$/.exec(href || "");
            if (citation) {
              const index = Number(citation[1]);
              return (
                <a
                  {...props}
                  className="citation-mark"
                  href={href}
                  onClick={(event) => {
                    event.preventDefault();
                    onCitation(index);
                  }}
                >
                  {Children.count(linkChildren) ? linkChildren : index}
                </a>
              );
            }
            return (
              <a {...props} href={href} target="_blank" rel="noreferrer">
                {linkChildren}
              </a>
            );
          },
          pre: ({ children: codeChildren }) => <CodeFrame>{codeChildren}</CodeFrame>,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
