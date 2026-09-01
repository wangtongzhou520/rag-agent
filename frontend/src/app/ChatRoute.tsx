import { lazy, Suspense } from "react";

const ChatPage = lazy(() =>
  import("@/pages/ChatPage").then((module) => ({ default: module.ChatPage })),
);

export function ChatRoute() {
  return (
    <Suspense
      fallback={
        <div className="session-loading">
          <span />
          <p>正在载入问答工作区…</p>
        </div>
      }
    >
      <ChatPage />
    </Suspense>
  );
}
