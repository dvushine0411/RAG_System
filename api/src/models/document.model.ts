/**
 * api/src/models/document.model.ts
 * Mongoose model for document tracking and deduplication.
 * Ref: ARCHITECTURE.md §4.1 documents collection
 */

import mongoose, { Schema, Document } from "mongoose";

export interface IDocument extends Document {
  id: string;
  title: string;
  source_type: string;
  source_url?: string;
  file_hash: string;
  total_chunks: number;
  total_tokens: number;
  status: "pending" | "processing" | "completed" | "failed";
  metadata: Record<string, unknown>;
  createdAt: Date;
  updatedAt: Date;
}

const DocumentSchema = new Schema<IDocument>(
  {
    id: { type: String, required: true, unique: true },
    title: { type: String, required: true },
    source_type: { type: String, required: true },
    // No `default: null` — the MongoDB $jsonSchema validator requires a string when the field is present.
    source_url: { type: String },
    file_hash: { type: String, required: true, unique: true, index: true },
    total_chunks: { type: Number, default: 0 },
    total_tokens: { type: Number, default: 0 },
    status: {
      type: String,
      enum: ["pending", "processing", "completed", "failed"],
      default: "pending",
      index: true,
    },
    metadata: { type: Schema.Types.Mixed, default: {} },
  },
  {
    timestamps: true,
  }
);

export const DocumentModel =
  mongoose.models.Document || mongoose.model<IDocument>("Document", DocumentSchema);
