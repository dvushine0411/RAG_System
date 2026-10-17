/**
 * System Role: Maps an uploaded filename's extension to the canonical `source_type` stored in MongoDB.
 * Inputs: Original upload filename (e.g. "notes.md").
 * Outputs: Canonical source type ("pdf" | "docx" | "markdown" | "text" | "html") or null if unsupported.
 * Ref: ARCHITECTURE.md §4.1 documents collection (source_type enum in db/mongo_init validator)
 */

export type SourceType = "pdf" | "docx" | "markdown" | "text" | "html";

const EXTENSION_TO_SOURCE_TYPE: Record<string, SourceType> = {
  pdf: "pdf",
  docx: "docx",
  doc: "docx",
  md: "markdown",
  markdown: "markdown",
  txt: "text",
  text: "text",
  html: "html",
  htm: "html",
};

export const SUPPORTED_EXTENSIONS = Object.keys(EXTENSION_TO_SOURCE_TYPE);

export function resolveSourceType(filename: string): SourceType | null {
  const dotIndex = filename.lastIndexOf(".");
  if (dotIndex < 0) return null;
  const extension = filename.slice(dotIndex + 1).toLowerCase();
  return EXTENSION_TO_SOURCE_TYPE[extension] ?? null;
}
