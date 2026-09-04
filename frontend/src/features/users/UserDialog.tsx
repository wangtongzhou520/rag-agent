import { useEffect, useState, type FormEvent } from "react";

import type { ManagedUser, ManagedUserRole, UserWrite } from "@/features/users/types";
import { Button } from "@/shared/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/Dialog";
import { Input } from "@/shared/ui/Input";

export function UserDialog({
  open,
  current,
  busy,
  onClose,
  onSubmit,
}: {
  open: boolean;
  current?: ManagedUser;
  busy: boolean;
  onClose: () => void;
  onSubmit: (value: UserWrite) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<ManagedUserRole>("user");
  const [avatar, setAvatar] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setUsername(current?.username || "");
    setPassword("");
    setRole(current?.role || "user");
    setAvatar(current?.avatar || "");
    setError("");
  }, [current, open]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim()) {
      setError("用户名不能为空");
      return;
    }
    if (!current && !password.trim()) {
      setError("初始密码不能为空");
      return;
    }
    onSubmit({
      username: username.trim(),
      role,
      avatar: avatar.trim(),
      ...(password.trim() ? { password: password.trim() } : {}),
    });
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="user-dialog">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{current ? "编辑用户" : "新建用户"}</DialogTitle>
            <DialogDescription>
              {current
                ? "身份信息变化后，该用户现有登录会话会立即失效。"
                : "创建可登录工作台的新账号；默认角色为普通用户。"}
            </DialogDescription>
          </DialogHeader>
          <div className="user-form-grid">
            <label>
              <span>用户名</span>
              <Input
                autoFocus
                aria-label="用户名"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="例如：zhangsan"
              />
            </label>
            <label>
              <span>角色</span>
              <select
                aria-label="角色"
                value={role}
                onChange={(event) => setRole(event.target.value as ManagedUserRole)}
              >
                <option value="user">普通用户</option>
                <option value="admin">管理员</option>
              </select>
            </label>
            <label className="user-form-wide">
              <span>{current ? "重置密码（留空不修改）" : "初始密码"}</span>
              <Input
                aria-label={current ? "重置密码" : "初始密码"}
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <label className="user-form-wide">
              <span>头像地址（可选）</span>
              <Input
                aria-label="头像地址"
                value={avatar}
                onChange={(event) => setAvatar(event.target.value)}
                placeholder="https://…"
              />
            </label>
          </div>
          {error && <p className="console-form-error">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "正在保存…" : "保存用户"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
