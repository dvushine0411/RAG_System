/**
 * System Role: React state hook for the document library (list, upload, delete, retrieval scope selection).
 * Inputs: User actions from DocumentPanel.
 * Outputs: documents, selectedIds, busy/error state, and action callbacks.
 */

import { useCallback, useEffect, useState } from "react";
import { deleteDocument, listDocuments, uploadDocument } from "../api/documents.api";
import type { DocumentRecord } from "../types";

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
      setSelectedIds((ids) => ids.filter((id) => docs.some((d) => d.id === id)));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const upload = useCallback(
    async (files: File[]) => {
      setUploading(true);
      setError(null);
      setNotice(null);
      const messages: string[] = [];
      for (const file of files) {
        try {
          const result = await uploadDocument(file);
          messages.push(
            result.is_duplicate
              ? `“${file.name}” đã tồn tại (trùng nội dung).`
              : `Đã lập chỉ mục “${file.name}” (${result.document.total_chunks} chunk).`
          );
        } catch (err) {
          messages.push(`Lỗi “${file.name}”: ${err instanceof Error ? err.message : String(err)}`);
        }
      }
      setNotice(messages.join(" "));
      setUploading(false);
      await refresh();
    },
    [refresh]
  );

  const remove = useCallback(
    async (id: string) => {
      try {
        await deleteDocument(id);
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [refresh]
  );

  const toggleSelected = useCallback((id: string) => {
    setSelectedIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }, []);

  return { documents, selectedIds, uploading, error, notice, refresh, upload, remove, toggleSelected };
}
