import { ArrowLeft, Database, GitBranch, KeyRound, LogOut, Workflow } from "lucide-react";
import { Link, Outlet } from "react-router-dom";

import { useAuthStore } from "@/features/auth/store";
import { BrandMark } from "@/shared/components/BrandMark";
import { Button } from "@/shared/ui/Button";

const nextModules = [
  [Database, "知识库管理", "F2"],
  [GitBranch, "意图树", "F2"],
  [KeyRound, "查询词映射", "F2"],
  [Workflow, "链路追踪", "F2"],
] as const;

export function ConsoleLayout() {
  const { user, logout } = useAuthStore();
  return (
    <div className="console-layout">
      <aside className="console-sidebar">
        <BrandMark className="[&_strong]:text-white [&_span_span]:text-blue-100" />
        <nav aria-label="控制台模块">
          <p>即将接入</p>
          {nextModules.map(([Icon, label, phase]) => (
            <span className="console-nav-preview" key={label}>
              <Icon aria-hidden="true" />
              <span>{label}</span>
              <small>{phase}</small>
            </span>
          ))}
        </nav>
      </aside>
      <div className="console-main">
        <header className="console-topbar">
          <Button asChild variant="ghost">
            <Link to="/chat">
              <ArrowLeft className="h-4 w-4" />
              返回问答
            </Link>
          </Button>
          <div className="flex items-center gap-3 text-sm text-muted">
            <span>{user?.username}</span>
            <Button aria-label="退出登录" onClick={() => void logout()} variant="ghost">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>
        <Outlet />
      </div>
    </div>
  );
}
