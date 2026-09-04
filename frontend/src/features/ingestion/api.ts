import type {
  AsyncTask,
  Pipeline,
  PipelineTask,
  PipelineWrite,
  TaskNode,
} from "@/features/ingestion/types";
import { request } from "@/shared/api/client";
import { normalizePage, type PageResult } from "@/shared/api/result";

export async function listPipelines(pageNo: number, pageSize: number, keyword = "") {
  const page = await request<PageResult<Pipeline>>({
    method: "GET",
    url: "/ingestion/pipelines",
    params: { pageNo, pageSize, ...(keyword ? { keyword } : {}) },
  });
  return normalizePage(page);
}

export function createPipeline(value: PipelineWrite) {
  return request<string>({ method: "POST", url: "/ingestion/pipelines", data: value });
}

export function updatePipeline(id: number, value: PipelineWrite) {
  return request<null>({ method: "PUT", url: `/ingestion/pipelines/${id}`, data: value });
}

export function deletePipeline(id: number) {
  return request<null>({ method: "DELETE", url: `/ingestion/pipelines/${id}` });
}

export async function listPipelineTasks(pageNo: number, pageSize: number, status = "") {
  const page = await request<PageResult<PipelineTask>>({
    method: "GET",
    url: "/ingestion/tasks",
    params: { pageNo, pageSize, ...(status ? { status } : {}) },
  });
  return normalizePage(page);
}

export function getTaskNodes(id: number) {
  return request<TaskNode[]>({ method: "GET", url: `/ingestion/tasks/${id}/nodes` });
}

export async function listAsyncTasks(current: number, size: number, status = "") {
  const page = await request<PageResult<AsyncTask>>({
    method: "GET",
    url: "/ingestion/async-tasks",
    params: { current, size, ...(status ? { status } : {}) },
  });
  return normalizePage(page);
}

export function runUrlTask(value: {
  pipelineId: number;
  sourceType: "url" | "feishu";
  location: string;
  fileName?: string;
  vectorSpaceId?: string;
}) {
  return request<{ taskId: string; status: string; message: string }>({
    method: "POST",
    url: "/ingestion/tasks",
    data: {
      pipelineId: value.pipelineId,
      source: {
        type: value.sourceType,
        location: value.location,
        fileName: value.fileName || undefined,
      },
      metadata: {},
      vectorSpaceId: value.vectorSpaceId || undefined,
    },
  });
}

export function runUploadTask(pipelineId: number, file: File, vectorSpaceId?: string) {
  const body = new FormData();
  body.append("pipelineId", String(pipelineId));
  body.append("file", file);
  if (vectorSpaceId) body.append("vectorSpaceId", vectorSpaceId);
  return request<{ taskId: string; status: string; message: string }>({
    method: "POST",
    url: "/ingestion/tasks/upload",
    data: body,
  });
}
