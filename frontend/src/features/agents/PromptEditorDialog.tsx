import { Copy, RotateCcw } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import type { PromptSlot } from "@/features/agents/types";
import { Button } from "@/shared/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/Dialog";

export function PromptEditorDialog({
  open,
  slot,
  agentName,
  defaultAgentName,
  busy,
  onClose,
  onLoadDefault,
  onSubmit,
}: {
  open: boolean;
  slot?: PromptSlot;
  agentName: string;
  defaultAgentName: string;
  busy: boolean;
  onClose: () => void;
  onLoadDefault: () => Promise<string>;
  onSubmit: (content: string) => void;
}) {
  const [content, setContent] = useState("");
  const [loadingDefault, setLoadingDefault] = useState(false);

  useEffect(() => setContent(slot?.content || ""), [open, slot]);
  if (!slot) return null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit(content);
  };
  const copyDefault = async () => {
    setLoadingDefault(true);
    try {
      setContent(await onLoadDefault());
    } finally {
      setLoadingDefault(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="prompt-editor-dialog">
        <form onSubmit={submit}>
          <DialogHeader>
            <div className="prompt-editor-kicker">
              <span>{slot.groupName}</span>
              <code>{slot.slotKey}</code>
            </div>
            <DialogTitle>{slot.displayName}</DialogTitle>
            <DialogDescription>
              正在编辑「{agentName}」。留空保存后，运行时会回落到「{defaultAgentName}」。
            </DialogDescription>
          </DialogHeader>
          <div className="prompt-editor-tools">
            <Button type="button" variant="secondary" onClick={() => void copyDefault()}>
              <Copy aria-hidden="true" /> {loadingDefault ? "读取中…" : "从默认复制"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setContent("")}>
              <RotateCcw aria-hidden="true" /> 恢复默认
            </Button>
          </div>
          {slot.requiredPlaceholders.length > 0 && (
            <div className="prompt-placeholder-note">
              <span>必须保留</span>
              {slot.requiredPlaceholders.map((item) => (
                <code key={item}>{`{${item}}`}</code>
              ))}
            </div>
          )}
          <textarea
            className="prompt-editor-textarea"
            value={content}
            onChange={(event) => setContent(event.target.value)}
            spellCheck={false}
            aria-label={`${slot.displayName} Prompt 内容`}
          />
          <div className="prompt-editor-count">{content.length.toLocaleString()} 字符</div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "正在保存…" : "保存 Prompt"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
