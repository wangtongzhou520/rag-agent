export interface KnowledgeBase {
  id: number;
  name: string;
  embeddingModel: string;
  collectionName: string;
}

export interface KnowledgeBaseWrite {
  name: string;
  embeddingModel: string;
  collectionName: string;
}

export type DocumentStatus = "pending" | "running" | "success" | "failed";
export type DocumentSourceType = "file" | "url";

export interface IngestionSpec {
  version: number;
  parseProfile: string;
  budget: {
    maxChars: number;
    overlapChars: number;
    rowsPerChunk: number;
    toleranceFactor: number;
  };
}

export interface IngestionSpecSchema {
  version: number;
  parseProfiles: string[];
  budget: {
    maxChars: { default: number; min: number; max: number; whole: number };
    overlapChars: { default: number; min: number };
    rowsPerChunk: { default: number; min: number; max: number };
    toleranceFactor: { default: number };
  };
}

export interface KnowledgeDocument {
  id: number;
  kbId: number;
  docName: string;
  enabled: boolean;
  chunkCount: number;
  fileType?: string;
  mimeType?: string;
  fileSize?: number;
  status: DocumentStatus | string;
  sourceType: DocumentSourceType | string;
  sourceLocation?: string;
  ingestionSpec?: IngestionSpec;
}

export interface UploadDocumentInput {
  sourceType: DocumentSourceType;
  file?: File;
  sourceLocation?: string;
  ingestionSpec: IngestionSpec;
}

export interface KnowledgeChunk {
  id: string;
  docId: number;
  chunkIndex: number;
  content: string;
  enabled: boolean;
}
