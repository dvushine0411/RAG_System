/**
 * System Role: Sidebar UI for uploading, listing, deleting documents and choosing the retrieval scope.
 * Inputs: Props from useDocuments (documents, selection, actions); canManage (true only for admins).
 * Outputs: Rendered document library; upload & delete controls are shown only when canManage is true.
 */

import { useRef, useState, type DragEvent } from "react";
import { appConfig } from "../config";
import type { DocumentRecord } from "../types";

interface Props {
  documents: DocumentRecord[];
  selectedIds: string[];
  uploading: boolean;
  error: string | null;
  notice: string | null;
  onUpload: (files: File[]) => void;
  onDelete: (id: string) => void;
  onToggle: (id: string) => void;
  onRefresh: () => void;
  canManage: boolean;
}

const STATUS_LABEL: Record<DocumentRecord["status"], string> = {
  pending: "Chờ xử lý",
  processing: "Đang xử lý",
  completed: "Sẵn sàng",
  failed: "Lỗi",
};

export function DocumentPanel(props: Props) {
  const { documents, selectedIds, uploading, error, notice, onUpload, onDelete, onToggle, onRefresh, canManage } = props;
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = (list: FileList | null) => {
    if (list && list.length > 0) onUpload(Array.from(list));
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (!uploading) handleFiles(e.dataTransfer.files);
  };

  const confirmDelete = (doc: DocumentRecord) => {
    if (window.confirm(`Xoá “${doc.title}” và toàn bộ vector của nó?`)) onDelete(doc.id);
  };

  return (
    <section className="doc-panel">
      <div className="sidebar-header">
        <h2>Tài liệu</h2>
        <button className="ghost" onClick={onRefresh} title="Tải lại danh sách">
          ↻
        </button>
      </div>

      {canManage && (
      <div
        className={`dropzone${dragOver ? " drag" : ""}${uploading ? " busy" : ""}`}
        onClick={() => !uploading && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        {uploading ? "Đang tải lên & lập chỉ mục…" : "Kéo thả hoặc bấm để tải tài liệu"}
        <small>{appConfig.acceptedExtensions.join(" ")}</small>
        <input
          ref={inputRef}
          type="file"
          multiple
          hidden
          accept={appConfig.acceptedExtensions.join(",")}
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      )}

      {notice && <p className="notice">{notice}</p>}
      {error && <p className="error">{error}</p>}

      <p className="scope-hint">
        {selectedIds.length === 0
          ? "Đang tìm trong tất cả tài liệu. Tick để giới hạn phạm vi."
          : `Chỉ tìm trong ${selectedIds.length} tài liệu đã chọn.`}
      </p>

      <ul className="doc-list">
        {documents.length === 0 && <li className="empty">Chưa có tài liệu nào.</li>}
        {documents.map((doc) => (
          <li key={doc.id} className="doc-item">
            <label>
              <input
                type="checkbox"
                checked={selectedIds.includes(doc.id)}
                disabled={doc.status !== "completed"}
                onChange={() => onToggle(doc.id)}
              />
              <span className="doc-title" title={doc.title}>
                {doc.title}
              </span>
            </label>
            <div className="doc-meta">
              <span className={`badge status-${doc.status}`}>{STATUS_LABEL[doc.status]}</span>
              <span>{doc.source_type}</span>
              <span>{doc.total_chunks} chunk</span>
              {canManage && (
                <button className="ghost danger" onClick={() => confirmDelete(doc)} title="Xoá">
                  ✕
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
