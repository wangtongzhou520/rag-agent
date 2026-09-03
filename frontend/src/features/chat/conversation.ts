export function formatConversationTime(timestamp: number, now = Date.now()) {
  const date = new Date(timestamp);
  const current = new Date(now);
  if (date.toDateString() === current.toDateString()) {
    return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }
  if (date.getFullYear() === current.getFullYear()) {
    return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
  }
  return date.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}
