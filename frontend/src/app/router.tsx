import { Navigate, createBrowserRouter } from "react-router-dom";

import { ChatRoute } from "@/app/ChatRoute";
import { HomeRedirect, RequireAdmin, RequireAuth, SessionBootstrap } from "@/app/RouteGuards";
import { ConsoleLayout } from "@/layouts/ConsoleLayout";
import { KnowledgeBasePage } from "@/features/knowledge/KnowledgeBasePage";
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
      { path: "knowledge-bases", element: <KnowledgeBasePage /> },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]);
