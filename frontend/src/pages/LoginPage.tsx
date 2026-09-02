import { ArrowRight, KeyRound, UserRound } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { useAuthStore } from "@/features/auth/store";
import { BrandMark } from "@/shared/components/BrandMark";
import { Button } from "@/shared/ui/Button";
import { Input } from "@/shared/ui/Input";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { token, busy, login } = useAuthStore();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  if (token) return <Navigate to="/chat" replace />;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) {
      toast.error("请输入用户名和密码");
      return;
    }
    try {
      await login(username.trim(), password);
      const redirect = (location.state as { from?: string } | null)?.from || "/chat";
      navigate(redirect, { replace: true });
      toast.success("登录成功");
    } catch (error) {
      setPassword("");
      toast.error(error instanceof Error ? error.message : "登录失败");
    }
  };

  return (
    <main className="login-page">
      <section className="login-brand-panel" aria-label="Ragent AI 产品介绍">
        <div className="login-brand-panel__grid" aria-hidden="true" />
        <BrandMark className="relative z-10 [&_strong]:text-white [&_span_span]:text-blue-100" />
        <div className="login-brand-copy">
          <p className="login-eyebrow">Ragent 工作台</p>
          <h1>知识检索与问答，在一个工作区完成。</h1>
          <ul className="login-capabilities">
            <li>知识库与文档管理</li>
            <li>意图配置与检索控制</li>
            <li>回答来源与运行链路</li>
          </ul>
        </div>
      </section>

      <section className="login-form-panel">
        <form className="login-form" onSubmit={handleSubmit}>
          <div>
            <p className="login-form__kicker">欢迎回来</p>
            <h2>登录 Ragent AI</h2>
            <p className="login-form__hint">进入智能问答与知识管理工作台</p>
          </div>
          <label className="form-field">
            <span>用户名</span>
            <span className="form-field__control">
              <UserRound aria-hidden="true" />
              <Input
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="请输入用户名"
              />
            </span>
          </label>
          <label className="form-field">
            <span>密码</span>
            <span className="form-field__control">
              <KeyRound aria-hidden="true" />
              <Input
                autoComplete="current-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="请输入密码"
              />
            </span>
          </label>
          <Button className="mt-1 w-full" disabled={busy} type="submit">
            {busy ? "正在验证…" : "进入工作台"}
            {!busy && <ArrowRight aria-hidden="true" className="h-4 w-4" />}
          </Button>
          <p className="login-form__security">凭据仅发送至当前 Ragent API，不会写入浏览器日志。</p>
        </form>
      </section>
    </main>
  );
}
