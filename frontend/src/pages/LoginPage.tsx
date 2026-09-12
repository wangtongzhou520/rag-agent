import { ArrowRight } from "lucide-react";
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
      <div className="login-panel">
        <BrandMark />
        <form className="login-form" onSubmit={handleSubmit}>
          <header className="login-form__head">
            <h1>登录</h1>
            <p>使用管理员分配的账号进入工作台。</p>
          </header>
          <label className="form-field">
            <span>用户名</span>
            <Input
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="请输入用户名"
            />
          </label>
          <label className="form-field">
            <span>密码</span>
            <Input
              autoComplete="current-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="请输入密码"
            />
          </label>
          <Button className="login-form__submit w-full" disabled={busy} type="submit">
            {busy ? "正在验证…" : "登录"}
            {!busy && <ArrowRight aria-hidden="true" className="h-4 w-4" />}
          </Button>
        </form>
        <p className="login-panel__foot">账号由系统管理员分配，如有问题请联系管理员。</p>
      </div>
    </main>
  );
}
