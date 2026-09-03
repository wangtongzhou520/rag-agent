import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { deleteConversation, renameConversation } from "@/features/chat/api";
import { formatConversationTime } from "@/features/chat/conversation";
import type { ConversationSummary } from "@/features/chat/types";
import { cn } from "@/shared/lib/cn";
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

interface ConversationHistoryProps {
  conversations: ConversationSummary[];
  activeId?: string;
  loading: boolean;
  error?: string;
  onRetry: () => void;
  onOpen: (conversation: ConversationSummary) => void;
  onRenamed: (conversationId: string, title: string) => void;
  onDeleted: (conversationId: string) => void;
}

export function ConversationHistory({
  conversations,
  activeId,
  loading,
  error,
  onRetry,
  onOpen,
  onRenamed,
  onDeleted,
}: ConversationHistoryProps) {
  const queryClient = useQueryClient();
  const [menuId, setMenuId] = useState<string>();
  const [editing, setEditing] = useState<ConversationSummary>();
  const [deleting, setDeleting] = useState<ConversationSummary>();
  const [title, setTitle] = useState("");

  const rename = useMutation({
    mutationFn: () => renameConversation(editing?.conversationId || "", title.trim()),
    onSuccess: () => {
      if (editing) onRenamed(editing.conversationId, title.trim());
      setEditing(undefined);
      void queryClient.invalidateQueries({ queryKey: ["conversations"] });
      toast.success("会话已重命名");
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "重命名失败"),
  });
  const remove = useMutation({
    mutationFn: () => deleteConversation(deleting?.conversationId || ""),
    onSuccess: () => {
      if (deleting) onDeleted(deleting.conversationId);
      setDeleting(undefined);
      void queryClient.invalidateQueries({ queryKey: ["conversations"] });
      toast.success("会话已删除");
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "删除失败"),
  });

  return (
    <section className="conversation-history" aria-label="会话历史">
      <header>
        <span>最近会话</span>
        {!loading && <small>{conversations.length}</small>}
      </header>
      <div className="conversation-history__list">
        {loading ? (
          <p className="conversation-history__state">正在读取…</p>
        ) : error ? (
          <div className="conversation-history__state">
            <p>{error}</p>
            <button type="button" onClick={onRetry}>
              重新载入
            </button>
          </div>
        ) : conversations.length === 0 ? (
          <p className="conversation-history__state">首次提问后，会话会保存在这里。</p>
        ) : (
          conversations.map((conversation) => (
            <div
              className={cn(
                "conversation-history__item",
                conversation.conversationId === activeId && "is-active",
              )}
              key={conversation.conversationId}
            >
              <button
                type="button"
                onClick={() => {
                  setMenuId(undefined);
                  onOpen(conversation);
                }}
              >
                <strong>{conversation.title}</strong>
                <small>{formatConversationTime(conversation.lastTime)}</small>
              </button>
              <button
                className="conversation-history__more"
                type="button"
                aria-label={`管理 ${conversation.title}`}
                aria-expanded={menuId === conversation.conversationId}
                onClick={() =>
                  setMenuId((current) =>
                    current === conversation.conversationId
                      ? undefined
                      : conversation.conversationId,
                  )
                }
              >
                <MoreHorizontal aria-hidden="true" />
              </button>
              {menuId === conversation.conversationId && (
                <div className="conversation-history__menu" role="menu">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setTitle(conversation.title);
                      setEditing(conversation);
                      setMenuId(undefined);
                    }}
                  >
                    <Pencil aria-hidden="true" /> 重命名
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setDeleting(conversation);
                      setMenuId(undefined);
                    }}
                  >
                    <Trash2 aria-hidden="true" /> 删除
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <Dialog open={Boolean(editing)} onOpenChange={(open) => !open && setEditing(undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重命名会话</DialogTitle>
            <DialogDescription>标题用于在最近会话中快速定位，最多 30 个字符。</DialogDescription>
          </DialogHeader>
          <Input
            aria-label="会话标题"
            maxLength={30}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && title.trim()) void rename.mutateAsync();
            }}
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditing(undefined)}>
              取消
            </Button>
            <Button
              disabled={!title.trim() || rename.isPending}
              onClick={() => void rename.mutateAsync()}
            >
              保存标题
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除这个会话？</DialogTitle>
            <DialogDescription>
              “{deleting?.title}”及其消息记录会被删除，此操作无法从页面恢复。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleting(undefined)}>
              取消
            </Button>
            <Button disabled={remove.isPending} onClick={() => void remove.mutateAsync()}>
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
