import { CheckCircle2 } from "lucide-react";

import { RagSignalRail } from "@/shared/components/RagSignalRail";

export function AdminFoundationPage() {
  return (
    <main className="console-content">
      <div className="console-page-heading">
        <p>工程状态 / F0</p>
        <h1>前端基础设施</h1>
        <span>蓝色设计系统与应用框架已经建立，业务模块将在 F1/F2 接入。</span>
      </div>
      <section className="foundation-status-panel">
        <div>
          <span className="status-pill">
            <CheckCircle2 /> FOUNDATION READY
          </span>
          <h2>契约优先，页面随后。</h2>
          <p>API 解包、认证恢复、角色归一化、本地代理、查询缓存和测试框架均已形成统一边界。</p>
        </div>
        <RagSignalRail active={1} />
      </section>
    </main>
  );
}
