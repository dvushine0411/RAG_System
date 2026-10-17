/**
 * System Role: Client for document management endpoints of the API Gateway.
 * Inputs: File objects to upload, document ids to delete.
 * Outputs: DocumentRecord lists and UploadResult objects.
 * Endpoints: GET/POST /api/v1/documents, DELETE /api/v1/documents/:id
 */

import { apiFetch } from "./http";
import type { DocumentRecord, UploadResult } from "../types";

export async function listDocuments(): Promise<DocumentRecord[]> {
  const res = await apiFetch("/documents");
  const body = (await res.json()) as { documents: DocumentRecord[] };
  return body.documents;
}

export async function uploadDocument(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file, file.name);
  const res = await apiFetch("/documents", { method: "POST", body: form });
  return (await res.json()) as UploadResult;
}

export async function deleteDocument(id: string): Promise<void> {
  await apiFetch(`/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
}
