export type MappingMatchType = 1 | 2 | 3 | 4;

export interface QueryTermMappingWrite {
  sourceTerm: string;
  targetTerm: string;
  matchType: MappingMatchType;
  priority?: number | null;
  enabled: boolean;
  domain?: string | null;
  remark?: string | null;
}

export interface QueryTermMapping extends QueryTermMappingWrite {
  id: number;
}

export const MATCH_TYPE_LABELS: Record<MappingMatchType, string> = {
  1: "精确匹配",
  2: "前缀匹配",
  3: "正则匹配",
  4: "整词匹配",
};
