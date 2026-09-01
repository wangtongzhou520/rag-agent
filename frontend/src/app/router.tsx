import { createBrowserRouter } from "react-router-dom";

import { HomeRedirect, RequireAdmin, RequireAuth, SessionBootstrap } from "@/app/RouteGuards";
import { ConsoleLayout } from "@/layouts/ConsoleLayout";
import { AdminFoundationPage } from "@/pages/AdminFoundationPage";
import { ChatFoundationPage } from "@/pages/ChatFoundationPage";
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
          <ChatFoundationPage />
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
    children: [{ index: true, element: <AdminFoundationPage /> }],
  },
  { path: "*", element: <NotFoundPage /> },
]);
