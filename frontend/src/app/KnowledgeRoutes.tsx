import { lazy, Suspense, type ComponentType } from "react";

const KnowledgeBasePage = lazy(() =>
  import("@/features/knowledge/KnowledgeBasePage").then((module) => ({
    default: module.KnowledgeBasePage,
  })),
);
const DocumentPage = lazy(() =>
  import("@/features/knowledge/DocumentPage").then((module) => ({
    default: module.DocumentPage,
  })),
);
const ChunkPage = lazy(() =>
  import("@/features/knowledge/ChunkPage").then((module) => ({ default: module.ChunkPage })),
);

function KnowledgeRoute({ Page, label }: { Page: ComponentType; label: string }) {
  return (
    <Suspense
      fallback={
        <div className="session-loading console-route-loading">
          <span />
          <p>正在载入{label}…</p>
        </div>
      }
    >
      <Page />
    </Suspense>
  );
}

export function KnowledgeBaseRoute() {
  return <KnowledgeRoute Page={KnowledgeBasePage} label="知识库" />;
}

export function DocumentRoute() {
  return <KnowledgeRoute Page={DocumentPage} label="文档工作台" />;
}

export function ChunkRoute() {
  return <KnowledgeRoute Page={ChunkPage} label="Chunk 工作台" />;
}
