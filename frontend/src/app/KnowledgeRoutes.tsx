import { lazy, Suspense, type ComponentType } from "react";

const KnowledgeBasePage = lazy(() =>
  import("@/features/knowledge/KnowledgeBasePage").then((module) => ({
    default: module.KnowledgeBasePage,
  })),
);
const DashboardPage = lazy(() =>
  import("@/features/dashboard/DashboardPage").then((module) => ({
    default: module.DashboardPage,
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
const IntentTreePage = lazy(() =>
  import("@/features/intent/IntentTreePage").then((module) => ({
    default: module.IntentTreePage,
  })),
);
const MappingPage = lazy(() =>
  import("@/features/mapping/MappingPage").then((module) => ({
    default: module.MappingPage,
  })),
);
const TraceListPage = lazy(() =>
  import("@/features/trace/TraceListPage").then((module) => ({
    default: module.TraceListPage,
  })),
);
const TraceDetailPage = lazy(() =>
  import("@/features/trace/TraceDetailPage").then((module) => ({
    default: module.TraceDetailPage,
  })),
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

export function DashboardRoute() {
  return <KnowledgeRoute Page={DashboardPage} label="系统概览" />;
}

export function DocumentRoute() {
  return <KnowledgeRoute Page={DocumentPage} label="文档工作台" />;
}

export function ChunkRoute() {
  return <KnowledgeRoute Page={ChunkPage} label="Chunk 工作台" />;
}

export function IntentTreeRoute() {
  return <KnowledgeRoute Page={IntentTreePage} label="意图树" />;
}

export function MappingRoute() {
  return <KnowledgeRoute Page={MappingPage} label="查询词映射" />;
}

export function TraceListRoute() {
  return <KnowledgeRoute Page={TraceListPage} label="RAG Trace" />;
}

export function TraceDetailRoute() {
  return <KnowledgeRoute Page={TraceDetailPage} label="Trace 详情" />;
}
