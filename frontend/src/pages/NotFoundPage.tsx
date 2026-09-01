import { Link } from "react-router-dom";

import { Button } from "@/shared/ui/Button";

export function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-canvas px-6 text-center">
      <div>
        <p className="font-mono text-sm text-brand-600">404 / SIGNAL LOST</p>
        <h1 className="mt-3 text-3xl font-semibold text-ink">没有找到这个页面</h1>
        <p className="mt-3 text-muted">路由可能已变更，返回工作台继续。</p>
        <Button asChild className="mt-6">
          <Link to="/">返回首页</Link>
        </Button>
      </div>
    </main>
  );
}
