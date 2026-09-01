import { Navigate, createBrowserRouter } from "react-router-dom";

import { ChatRoute } from "@/app/ChatRoute";
import { ChunkRoute, DocumentRoute, KnowledgeBaseRoute } from "@/app/KnowledgeRoutes";
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
      { index: true, element: <Navigate to="knowledge-bases" replace /> },
      { path: "knowledge-bases", element: <KnowledgeBaseRoute /> },
      { path: "knowledge-bases/:kbId/documents", element: <DocumentRoute /> },
      { path: "documents/:docId/chunks", element: <ChunkRoute /> },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]);
