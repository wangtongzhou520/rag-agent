import { useEffect, useState, type FormEvent } from "react";

import type { PasswordChange } from "@/features/users/types";
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

export function PasswordDialog({
  open,
  busy,
  onClose,
  onSubmit,
}: {
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onSubmit: (value: PasswordChange) => void;
}) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setError("");
  }, [open]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!currentPassword || !newPassword.trim()) {
      setError("当前密码和新密码均不能为空");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("两次输入的新密码不一致");
      return;
    }
    onSubmit({ currentPassword, newPassword: newPassword.trim() });
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="password-dialog">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>修改我的密码</DialogTitle>
            <DialogDescription>修改成功后当前设备及其他设备都会退出登录。</DialogDescription>
          </DialogHeader>
          <div className="user-form-grid user-form-grid--single">
            <label>
              <span>当前密码</span>
              <Input
                aria-label="当前密码"
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
              />
            </label>
            <label>
              <span>新密码</span>
              <Input
                aria-label="新密码"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
              />
            </label>
            <label>
              <span>确认新密码</span>
              <Input
                aria-label="确认新密码"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
              />
            </label>
          </div>
          {error && <p className="console-form-error">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "正在修改…" : "确认修改"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
