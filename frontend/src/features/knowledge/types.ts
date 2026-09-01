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
