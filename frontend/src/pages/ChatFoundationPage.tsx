import { ArrowRight, Database, LogOut, MessageSquareText, Workflow } from "lucide-react";
import { Link } from "react-router-dom";

import { useAuthStore } from "@/features/auth/store";
import { BrandMark } from "@/shared/components/BrandMark";
import { RagSignalRail } from "@/shared/components/RagSignalRail";
import { Button } from "@/shared/ui/Button";

export function ChatFoundationPage() {
  const { user, logout } = useAuthStore();

  return (
    <main className="foundation-page">
      <header className="foundation-header">
        <BrandMark />
        <div className="flex items-center gap-2">
          {user?.role === "admin" && (
            <Button asChild variant="secondary">
              <Link to="/admin">管理控制台</Link>
            </Button>
          )}
          <Button aria-label="退出登录" onClick={() => void logout()} variant="ghost">
            <LogOut className="h-4 w-4" />
            退出
          </Button>
        </div>
      </header>
      <section className="foundation-hero">
        <p className="foundation-eyebrow">FRONTEND FOUNDATION · F0</p>
        <h1>蓝色工作台基础已经就绪。</h1>
        <p>认证、路由、API 契约和设计 Token 已接入。下一阶段将在这里承载真实 SSE 问答。</p>
        <div className="foundation-rail">
          <RagSignalRail active={1} />
        </div>
        <div className="foundation-cards">
          <article>
            <MessageSquareText />
            <strong>智能问答</strong>
            <span>F1 · SSE 与来源引用</span>
          </article>
          <article>
            <Database />
            <strong>知识管理</strong>
            <span>F2 · 文档与 Chunk</span>
          </article>
          <article>
            <Workflow />
            <strong>链路观测</strong>
            <span>F2 · RAG Trace</span>
          </article>
        </div>
        {user?.role === "admin" && (
          <Button asChild className="mt-7">
            <Link to="/admin">
              查看控制台框架 <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        )}
      </section>
    </main>
  );
}
