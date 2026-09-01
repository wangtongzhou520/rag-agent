import { useEffect, type PropsWithChildren } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuthStore } from "@/features/auth/store";

export function SessionBootstrap({ children }: PropsWithChildren) {
  const { ready, initialize } = useAuthStore();

  useEffect(() => {
    if (!ready) void initialize();
  }, [initialize, ready]);

  if (!ready) {
    return (
      <div className="session-loading">
        <span />
        <p>正在恢复工作台…</p>
      </div>
    );
  }

  return children;
}

export function RequireAuth({ children }: PropsWithChildren) {
  const location = useLocation();
  const token = useAuthStore((state) => state.token);

  if (!token) {
    return (
      <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />
    );
  }

  return children;
}

export function RequireAdmin({ children }: PropsWithChildren) {
  const user = useAuthStore((state) => state.user);
  if (user?.role !== "admin") return <Navigate to="/chat" replace />;
  return children;
}

export function HomeRedirect() {
  const token = useAuthStore((state) => state.token);
  return <Navigate to={token ? "/chat" : "/login"} replace />;
}
