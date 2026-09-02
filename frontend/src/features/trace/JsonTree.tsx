import { ChevronRight } from "lucide-react";

function primitive(value: unknown) {
  if (value === null) return <span className="json-null">null</span>;
  if (typeof value === "string") return <span className="json-string">“{value}”</span>;
  if (typeof value === "number") return <span className="json-number">{value}</span>;
  if (typeof value === "boolean") return <span className="json-boolean">{String(value)}</span>;
  return <span>{String(value)}</span>;
}

function JsonBranch({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (typeof value !== "object" || value === null) return primitive(value);
  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index), item] as const)
    : Object.entries(value as Record<string, unknown>);
  const braces = Array.isArray(value) ? ["[", "]"] : ["{", "}"];
  if (!entries.length) return <span>{braces.join("")}</span>;

  return (
    <details className="json-branch" open={depth < 2}>
      <summary>
        <ChevronRight aria-hidden="true" />
        <span>{braces[0]}</span>
        <small>{entries.length} 项</small>
      </summary>
      <div>
        {entries.map(([key, item]) => (
          <div className="json-row" key={key}>
            <span className="json-key">{Array.isArray(value) ? key : `“${key}”`}:</span>
            <JsonBranch value={item} depth={depth + 1} />
          </div>
        ))}
        <span className="json-brace">{braces[1]}</span>
      </div>
    </details>
  );
}

export function JsonTree({ value }: { value: Record<string, unknown> | null | undefined }) {
  return (
    <div className="json-tree">
      <JsonBranch value={value || {}} />
    </div>
  );
}
