import { useEffect, useState, type FormEvent } from "react";

import type { AgentProfile, AgentProfileWrite } from "@/features/agents/types";
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

const avatars = ["compass", "archive", "briefcase", "book-open", "scan-search"];

export function AgentDialog({
  open,
  current,
  busy,
  onClose,
  onSubmit,
}: {
  open: boolean;
  current?: AgentProfile;
  busy: boolean;
  onClose: () => void;
  onSubmit: (value: AgentProfileWrite) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [avatar, setAvatar] = useState(avatars[0]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setName(current?.name || "");
    setDescription(current?.description || "");
    setAvatar(current?.avatar || avatars[0]);
    setError("");
  }, [current, open]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError("智能体名称不能为空");
      return;
    }
    onSubmit({ name: name.trim(), description: description.trim(), avatar });
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="agent-profile-dialog">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{current ? "编辑智能体" : "新建智能体"}</DialogTitle>
            <DialogDescription>
              人设用于组织一组 Prompt 配置；新建后不会自动切换线上生效配置。
            </DialogDescription>
          </DialogHeader>
          <div className="agent-profile-form">
            <label>
              <span>名称</span>
              <Input
                autoFocus
                value={name}
                maxLength={64}
                onChange={(event) => setName(event.target.value)}
                placeholder="例如：产品支持"
              />
            </label>
            <label>
              <span>说明</span>
              <textarea
                value={description}
                maxLength={512}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="说明适用业务和回答边界"
              />
            </label>
            <fieldset>
              <legend>识别标记</legend>
              <div className="agent-avatar-options">
                {avatars.map((item, index) => (
                  <button
                    type="button"
                    key={item}
                    className={avatar === item ? "active" : ""}
                    onClick={() => setAvatar(item)}
                    aria-label={`选择标记 ${index + 1}`}
                  >
                    {String(index + 1).padStart(2, "0")}
                  </button>
                ))}
              </div>
            </fieldset>
          </div>
          {error && <p className="agent-form-error">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "正在保存…" : "保存智能体"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
