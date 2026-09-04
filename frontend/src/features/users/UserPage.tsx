import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Edit3,
  KeyRound,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  UsersRound,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { useAuthStore } from "@/features/auth/store";
import {
  changePassword,
  createUser,
  deleteUser,
  listUsers,
  updateUser,
} from "@/features/users/api";
import { PasswordDialog } from "@/features/users/PasswordDialog";
import type { ManagedUser, UserWrite } from "@/features/users/types";
import { UserDialog } from "@/features/users/UserDialog";
import { formatTraceTime } from "@/features/trace/format";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/Table";

const PAGE_SIZE = 20;

export function UserPage() {
  const queryClient = useQueryClient();
  const clearAuth = useAuthStore((state) => state.clear);
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const keyword = params.get("keyword")?.trim() || "";
  const [search, setSearch] = useState(keyword);
  const [editing, setEditing] = useState<ManagedUser>();
  const [deleting, setDeleting] = useState<ManagedUser>();
  const [formOpen, setFormOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);

  useEffect(() => setSearch(keyword), [keyword]);
  const query = useQuery({
    queryKey: ["users", page, keyword],
    queryFn: () => listUsers(page, PAGE_SIZE, keyword),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["users"] });
  const save = useMutation({
    mutationFn: (value: UserWrite) =>
      editing
        ? updateUser(editing.id, value)
        : createUser(value as Required<Pick<UserWrite, "username" | "password">> & UserWrite),
    onSuccess: () => {
      toast.success(editing ? "用户已更新" : "用户已创建");
      setFormOpen(false);
      setEditing(undefined);
      void refresh();
      void queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "用户保存失败"),
  });
  const remove = useMutation({
    mutationFn: (id: number) => deleteUser(id),
    onSuccess: () => {
      toast.success("用户已删除");
      setDeleting(undefined);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "用户删除失败"),
  });
  const password = useMutation({
    mutationFn: changePassword,
    onSuccess: () => {
      toast.success("密码已修改，请重新登录");
      setPasswordOpen(false);
      window.setTimeout(clearAuth, 500);
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "密码修改失败"),
  });

  const updateLocation = (nextPage: number, nextKeyword = keyword) => {
    const next = new URLSearchParams();
    if (nextKeyword) next.set("keyword", nextKeyword);
    if (nextPage > 1) next.set("page", String(nextPage));
    setParams(next);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    updateLocation(1, search.trim());
  };

  return (
    <main className="console-content user-page">
      <header className="console-page-header">
        <div className="console-page-heading">
          <p>系统管理</p>
          <h1>用户管理</h1>
          <span>维护登录账号和角色；敏感变更会立即清理该用户的全部会话。</span>
        </div>
        <div className="user-header-actions">
          <Button variant="secondary" onClick={() => setPasswordOpen(true)}>
            <KeyRound aria-hidden="true" /> 修改我的密码
          </Button>
          <Button
            onClick={() => {
              setEditing(undefined);
              setFormOpen(true);
            }}
          >
            <Plus aria-hidden="true" /> 新建用户
          </Button>
        </div>
      </header>
      <section className="console-toolbar user-toolbar">
        <form onSubmit={submit}>
          <Search aria-hidden="true" />
          <Input
            aria-label="搜索用户"
            placeholder="搜索用户名或角色"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </form>
        <Button variant="secondary" onClick={() => void query.refetch()}>
          <RefreshCw aria-hidden="true" /> 刷新
        </Button>
      </section>
      <section className="knowledge-table-panel user-table-panel">
        {query.isLoading ? (
          <div className="console-table-state">正在读取用户…</div>
        ) : query.isError ? (
          <div className="console-table-state console-table-state--error">
            {query.error instanceof Error ? query.error.message : "用户加载失败"}
          </div>
        ) : query.data?.records.length === 0 ? (
          <div className="console-empty-state">
            <UsersRound aria-hidden="true" />
            <strong>{keyword ? "没有匹配的用户" : "还没有可管理用户"}</strong>
            <p>{keyword ? "尝试调整搜索关键词。" : "创建第一个业务账号。"}</p>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>用户</TableHead>
                  <TableHead>角色</TableHead>
                  <TableHead>创建时间</TableHead>
                  <TableHead>最近更新</TableHead>
                  <TableHead className="w-[110px] text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data?.records.map((item) => {
                  const protectedUser = item.username.toLowerCase() === "admin";
                  return (
                    <TableRow key={item.id}>
                      <TableCell>
                        <div className="user-identity">
                          <span>{item.username.slice(0, 1).toUpperCase()}</span>
                          <div>
                            <strong>{item.username}</strong>
                            <small>
                              ID {item.id}
                              {protectedUser ? " · 默认管理员" : ""}
                            </small>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className={`user-role user-role--${item.role}`}>
                          {item.role === "admin" ? (
                            <ShieldCheck aria-hidden="true" />
                          ) : (
                            <UsersRound aria-hidden="true" />
                          )}
                          {item.role === "admin" ? "管理员" : "普通用户"}
                        </span>
                      </TableCell>
                      <TableCell>
                        <time>{formatTraceTime(item.createTime)}</time>
                      </TableCell>
                      <TableCell>
                        <time>{formatTraceTime(item.updateTime)}</time>
                      </TableCell>
                      <TableCell>
                        <div className="table-actions">
                          <button
                            type="button"
                            disabled={protectedUser}
                            aria-label={`编辑 ${item.username}`}
                            title={protectedUser ? "默认管理员不可修改" : undefined}
                            onClick={() => {
                              setEditing(item);
                              setFormOpen(true);
                            }}
                          >
                            <Edit3 aria-hidden="true" />
                          </button>
                          <button
                            type="button"
                            disabled={protectedUser}
                            aria-label={`删除 ${item.username}`}
                            title={protectedUser ? "默认管理员不可删除" : undefined}
                            onClick={() => setDeleting(item)}
                          >
                            <Trash2 aria-hidden="true" />
                          </button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            <footer className="console-pagination">
              <span>共 {query.data?.total || 0} 个用户</span>
              <div>
                <Button
                  variant="ghost"
                  disabled={page <= 1}
                  onClick={() => updateLocation(page - 1)}
                >
                  上一页
                </Button>
                <span>
                  {page} / {query.data?.pages || 1}
                </span>
                <Button
                  variant="ghost"
                  disabled={page >= (query.data?.pages || 1)}
                  onClick={() => updateLocation(page + 1)}
                >
                  下一页
                </Button>
              </div>
            </footer>
          </>
        )}
      </section>
      <UserDialog
        open={formOpen}
        current={editing}
        busy={save.isPending}
        onClose={() => {
          setFormOpen(false);
          setEditing(undefined);
        }}
        onSubmit={(value) => save.mutate(value)}
      />
      <PasswordDialog
        open={passwordOpen}
        busy={password.isPending}
        onClose={() => setPasswordOpen(false)}
        onSubmit={(value) => password.mutate(value)}
      />
      <Dialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除用户“{deleting?.username}”？</DialogTitle>
            <DialogDescription>
              该账号会被逻辑删除，现有登录会话将立即失效；历史业务数据和审计记录仍保留。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleting(undefined)}>
              取消
            </Button>
            <Button
              className="bg-[var(--danger)] hover:bg-red-700"
              disabled={remove.isPending}
              onClick={() => deleting && remove.mutate(deleting.id)}
            >
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
