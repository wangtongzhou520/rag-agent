import type { IntentNode } from "@/features/intent/types";

export function flattenIntentTree(roots: IntentNode[]): IntentNode[] {
  return roots.flatMap((node) => [node, ...flattenIntentTree(node.children)]);
}

export function intentBranchIds(node: IntentNode): number[] {
  return [node.id, ...node.children.flatMap(intentBranchIds)];
}

export function intentTreeStats(roots: IntentNode[]) {
  const nodes = flattenIntentTree(roots);
  return {
    total: nodes.length,
    enabled: nodes.filter((node) => node.enabled).length,
    leaves: nodes.filter((node) => node.level === 2).length,
  };
}
