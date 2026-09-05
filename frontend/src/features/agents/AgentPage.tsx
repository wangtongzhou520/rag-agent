import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronRight,
  CircleSlash2,
  Edit3,
  FilePenLine,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import "@/features/agents/AgentPage.css";
import { AgentDialog } from "@/features/agents/AgentDialog";
import {
  activateAgent,
  createAgent,
  deleteAgent,
  getAgentPrompts,
  getDefaultPrompt,
  listAgents,
  saveAgentPrompt,
  updateAgent,
} from "@/features/agents/api";
import { PromptEditorDialog } from "@/features/agents/PromptEditorDialog";
import type {
  AgentProfile,
  AgentProfileWrite,
  PromptGroup,
  PromptSlot,
} from "@/features/agents/types";
import { Button } from "@/shared/ui/Button";

const groups: PromptGroup[] = ["WORKFLOW", "AGENT", "COMMON"];

export function AgentPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number>();
  const [profileOpen, setProfileOpen] = useState(false);
  const [editing, setEditing] = useState<AgentProfile>();
  const [promptSlot, setPromptSlot] = useState<PromptSlot>();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const records = useMemo(() => agents.data?.agents || [], [agents.data?.agents]);

  useEffect(() => {
    if (!records.length) return;
    if (!selectedId || !records.some((item) => item.id === selectedId)) {
      setSelectedId(records.find((item) => item.active)?.id || records[0].id);
    }
  }, [records, selectedId]);

  const prompts = useQuery({
    queryKey: ["agent-prompts", selectedId],
    queryFn: () => getAgentPrompts(selectedId!),
    enabled: Boolean(selectedId),
  });
  const selected = records.find((item) => item.id === selectedId);
  const grouped = useMemo(
    () =>
      groups
        .map((group) => ({
          group,
          name: prompts.data?.slots.find((item) => item.group === group)?.groupName || group,
          slots: prompts.data?.slots.filter((item) => item.group === group) || [],
        }))
        .filter((item) => item.slots.length),
    [prompts.data],
  );

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["agents"] });
    void queryClient.invalidateQueries({ queryKey: ["agent-prompts"] });
  };
  const profileSave = useMutation({
    mutationFn: (value: AgentProfileWrite) =>
      editing ? updateAgent(editing.id, value) : createAgent(value),
    onSuccess: () => {
      toast.success(editing ? "智能体已更新" : "智能体已创建");
      setProfileOpen(false);
      setEditing(undefined);
      refresh();
    },
    onError: showError,
  });
  const activate = useMutation({
    mutationFn: activateAgent,
    onSuccess: () => {
      toast.success("生效配置已切换");
      refresh();
    },
    onError: showError,
  });
  const remove = useMutation({
    mutationFn: deleteAgent,
    onSuccess: () => {
      toast.success("智能体已删除");
      refresh();
    },
    onError: showError,
  });
  const promptSave = useMutation({
    mutationFn: (value: { slotKey: string; content: string }) =>
      saveAgentPrompt(selectedId!, value.slotKey, value.content),
    onSuccess: () => {
      toast.success("Prompt 已保存，运行时缓存已刷新");
      setPromptSlot(undefined);
      refresh();
    },
    onError: showError,
  });

  return (
    <main className="console-content agent-page">
      <header className="console-page-header agent-page-header">
        <div className="console-page-heading">
          <p>运行配置</p>
          <h1>智能体与 Prompt</h1>
          <span>维护可切换的人设版本，并确认每个 Prompt 槽位在当前架构中的实际状态。</span>
        </div>
        <div className="agent-header-actions">
          <Button variant="secondary" onClick={refresh}>
            <RefreshCw aria-hidden="true" /> 刷新
          </Button>
          <Button
            onClick={() => {
              setEditing(undefined);
              setProfileOpen(true);
            }}
          >
            <Plus aria-hidden="true" /> 新建智能体
          </Button>
        </div>
      </header>

      <section className="agent-mode-strip">
        <div>
          <span>当前执行架构</span>
          <strong>{agents.data?.mode || "—"}</strong>
        </div>
        <p>
          当前架构共有 <b>{agents.data?.effectiveSlotTotal ?? 0}</b>{" "}
          个可执行槽位。未生效配置会保留，切换架构后再参与运行。
        </p>
      </section>

      <div className="agent-workbench">
        <aside className="agent-profile-panel">
          <header>
            <div>
              <span>配置版本</span>
              <strong>{records.length}</strong>
            </div>
            <small>仅一项可处于生效状态</small>
          </header>
          <div className="agent-profile-list">
            {agents.isLoading ? (
              <PageState text="正在读取智能体…" />
            ) : agents.isError ? (
              <PageState text={errorText(agents.error)} error />
            ) : (
              records.map((item, index) => (
                <button
                  className={`agent-profile-card${selectedId === item.id ? " active" : ""}`}
                  key={item.id}
                  onClick={() => setSelectedId(item.id)}
                >
                  <span className="agent-profile-index">{String(index + 1).padStart(2, "0")}</span>
                  <span className="agent-profile-copy">
                    <strong>{item.name}</strong>
                    <small>{item.description || "未填写用途说明"}</small>
                    <span className="agent-profile-tags">
                      {item.active && <i className="is-active">生效中</i>}
                      {item.builtin && <i>系统内置</i>}
                      <i>{item.effectiveSlots} 项配置生效</i>
                    </span>
                  </span>
                  <ChevronRight aria-hidden="true" />
                </button>
              ))
            )}
          </div>
        </aside>

        <section className="agent-prompt-panel">
          {!selected ? (
            <PageState text="请选择一个智能体" />
          ) : (
            <>
              <header className="agent-prompt-header">
                <div>
                  <span>{selected.builtin ? "系统基线" : `配置 #${selected.id}`}</span>
                  <h2>{selected.name}</h2>
                  <p>{selected.description || "未填写用途说明"}</p>
                </div>
                {!selected.builtin && (
                  <div>
                    {!selected.active && (
                      <Button
                        variant="secondary"
                        disabled={activate.isPending}
                        onClick={() => activate.mutate(selected.id)}
                      >
                        <Check aria-hidden="true" /> 设为生效
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setEditing(selected);
                        setProfileOpen(true);
                      }}
                    >
                      <Edit3 aria-hidden="true" /> 编辑资料
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={selected.active || remove.isPending}
                      onClick={() => {
                        if (window.confirm(`确认删除「${selected.name}」及其 Prompt 配置？`)) {
                          remove.mutate(selected.id);
                        }
                      }}
                    >
                      <Trash2 aria-hidden="true" /> 删除
                    </Button>
                  </div>
                )}
              </header>

              {prompts.isLoading ? (
                <PageState text="正在读取 Prompt 槽位…" />
              ) : prompts.isError ? (
                <PageState text={errorText(prompts.error)} error />
              ) : (
                <div className="agent-slot-groups">
                  {grouped.map((section) => (
                    <section className="agent-slot-group" key={section.group}>
                      <header>
                        <h3>{section.name}</h3>
                        <span>{section.slots.length} 个槽位</span>
                      </header>
                      <div>
                        {section.slots.map((slot) => (
                          <article
                            className={`agent-slot-card${slot.effective ? "" : " inactive"}`}
                            key={slot.slotKey}
                          >
                            <div className="agent-slot-state">
                              {slot.effective ? <Check /> : <CircleSlash2 />}
                            </div>
                            <div className="agent-slot-copy">
                              <div>
                                <strong>{slot.displayName}</strong>
                                <code>{slot.slotKey}</code>
                              </div>
                              <p>
                                {!slot.effective
                                  ? slot.inactiveReason
                                  : slot.content
                                    ? "已配置当前智能体内容"
                                    : `未配置，运行时回落到「${prompts.data?.defaultAgentName}」`}
                              </p>
                              {slot.requiredPlaceholders.length > 0 && (
                                <span>
                                  占位符：
                                  {slot.requiredPlaceholders.map((item) => `{${item}}`).join(" · ")}
                                </span>
                              )}
                            </div>
                            <div className="agent-slot-actions">
                              <i className={slot.content ? "configured" : "fallback"}>
                                {slot.content ? "已配置" : "默认回落"}
                              </i>
                              {!selected.builtin && (
                                <button onClick={() => setPromptSlot(slot)}>
                                  <FilePenLine aria-hidden="true" /> 编辑
                                </button>
                              )}
                            </div>
                          </article>
                        ))}
                      </div>
                    </section>
                  ))}
                </div>
              )}
            </>
          )}
        </section>
      </div>

      <AgentDialog
        open={profileOpen}
        current={editing}
        busy={profileSave.isPending}
        onClose={() => {
          setProfileOpen(false);
          setEditing(undefined);
        }}
        onSubmit={(value) => profileSave.mutate(value)}
      />
      <PromptEditorDialog
        open={Boolean(promptSlot)}
        slot={promptSlot}
        agentName={selected?.name || ""}
        defaultAgentName={prompts.data?.defaultAgentName || "默认助手"}
        busy={promptSave.isPending}
        onClose={() => setPromptSlot(undefined)}
        onLoadDefault={() => getDefaultPrompt(promptSlot!.slotKey)}
        onSubmit={(content) => promptSave.mutate({ slotKey: promptSlot!.slotKey, content })}
      />
    </main>
  );
}

function PageState({ text, error = false }: { text: string; error?: boolean }) {
  return <div className={`agent-page-state${error ? " error" : ""}`}>{text}</div>;
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "数据加载失败";
}

function showError(error: unknown) {
  toast.error(errorText(error));
}
