import { Navigate, createBrowserRouter } from "react-router-dom";

import { ChatRoute } from "@/app/ChatRoute";
import {
  AuditRoute,
  ChunkRoute,
  DashboardRoute,
  DocumentRoute,
  IntentTreeRoute,
  KnowledgeBaseRoute,
  MappingRoute,
  TraceDetailRoute,
  TraceListRoute,
  UserRoute,
} from "@/app/KnowledgeRoutes";
import { HomeRedirect, RequireAdmin, RequireAuth, SessionBootstrap } from "@/app/RouteGuards";
import { ConsoleLayout } from "@/layouts/ConsoleLayout";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: (
      <SessionBootstrap>
        <HomeRedirect />
      </SessionBootstrap>
    ),
  },
  {
    path: "/login",
    element: (
      <SessionBootstrap>
        <LoginPage />
      </SessionBootstrap>
    ),
  },
  {
    path: "/chat",
    element: (
      <SessionBootstrap>
        <RequireAuth>
          <ChatRoute />
        </RequireAuth>
      </SessionBootstrap>
    ),
  },
  {
    path: "/chat/:conversationId",
    element: (
      <SessionBootstrap>
        <RequireAuth>
          <ChatRoute />
        </RequireAuth>
      </SessionBootstrap>
    ),
  },
  {
    path: "/admin",
    element: (
      <SessionBootstrap>
        <RequireAuth>
          <RequireAdmin>
            <ConsoleLayout />
          </RequireAdmin>
        </RequireAuth>
      </SessionBootstrap>
    ),
    children: [
      { index: true, element: <Navigate to="dashboard" replace /> },
      { path: "dashboard", element: <DashboardRoute /> },
      { path: "users", element: <UserRoute /> },
      { path: "audit-logs", element: <AuditRoute /> },
      { path: "knowledge-bases", element: <KnowledgeBaseRoute /> },
      { path: "knowledge-bases/:kbId/documents", element: <DocumentRoute /> },
      { path: "documents/:docId/chunks", element: <ChunkRoute /> },
      { path: "intent-tree", element: <IntentTreeRoute /> },
      { path: "mappings", element: <MappingRoute /> },
      { path: "traces", element: <TraceListRoute /> },
      { path: "traces/:traceId", element: <TraceDetailRoute /> },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]);
