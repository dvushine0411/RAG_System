/**
 * System Role: Fastify route handlers managing document upload lifecycle, SHA-256 deduplication, and vector purging.
 * Inputs: Multipart HTTP upload requests and document UUIDs.
 * Outputs: Ingested document records, deduplication match notifications, and deletion statuses.
 * Ref: ARCHITECTURE.md §2.2 Phase A & §4.1 Centralized Config Principle
 * Auth: GET requires a valid access token; POST / DELETE additionally require role "admin".
 */

import { randomUUID } from "node:crypto";
import { FastifyInstance, FastifyPluginAsync } from "fastify";
import "@fastify/multipart";
import { deduplicationService } from "../services/deduplication.service.js";
import { ragEngineClient } from "../services/rag-engine.client.js";
import { DocumentModel } from "../models/document.model.js";
import { logger } from "../config/logger.js";
import { resolveSourceType, SUPPORTED_EXTENSIONS } from "../utils/source-type.js";
import { requireAuth, requireRole } from "../middlewares/auth.middleware.js";

export const documentsRoute: FastifyPluginAsync = async (server: FastifyInstance) => {
  /**
   * POST /api/v1/documents
   * Receives multipart document, checks SHA-256 deduplication,
   * triggers Python RAG engine end-to-end ingestion (parse, chunk, embed, Qdrant upsert).
   */
  server.post("/documents", { preHandler: [requireAuth, requireRole("admin")] }, async (req, reply) => {
    // 1. Process multipart file stream
    const part = await req.file();
    if (!part) {
      return reply.status(400).send({
        error: "Bad Request",
        message: "No file attached in multipart form.",
      });
    }

    const buffer = await part.toBuffer();
    if (buffer.length === 0) {
      return reply.status(400).send({
        error: "Bad Request",
        message: "Uploaded file is empty.",
      });
    }

    const filename = part.filename;
    const sourceType = resolveSourceType(filename);
    if (!sourceType) {
      return reply.status(415).send({
        error: "Unsupported Media Type",
        message: `Unsupported file type for '${filename}'. Supported: ${SUPPORTED_EXTENSIONS.join(", ")}.`,
      });
    }

    const fileHash = deduplicationService.computeFileHash(buffer);
    logger.info(`[DocumentsRoute] Ingesting '${filename}' (SHA-256: ${fileHash.substring(0, 8)}...)`);

    // 2. Deduplication check against MongoDB
    const existingDoc = await deduplicationService.findDuplicate(fileHash);
    if (existingDoc && existingDoc.status === "failed") {
      // A previous ingestion of this exact file failed: drop the stale record so it can be retried.
      logger.info(`[DocumentsRoute] Retrying previously failed document '${existingDoc.id}'`);
      await DocumentModel.deleteOne({ id: existingDoc.id }).exec();
    } else if (existingDoc) {
      logger.info(`[DocumentsRoute] Duplicate detected for file: '${filename}'`);
      return reply.status(200).send({
        status: "success",
        is_duplicate: true,
        message: "Document already exists with identical content (deduplicated).",
        document: {
          id: existingDoc.id,
          title: existingDoc.title,
          source_type: existingDoc.source_type,
          file_hash: existingDoc.file_hash,
          total_chunks: existingDoc.total_chunks,
          total_tokens: existingDoc.total_tokens,
          status: existingDoc.status,
          createdAt: existingDoc.createdAt,
        },
      });
    }

    // 3. New Document: Create pending record in MongoDB
    const documentId = randomUUID();

    const newDoc = new DocumentModel({
      id: documentId,
      title: filename,
      source_type: sourceType,
      file_hash: fileHash,
      status: "processing",
      metadata: {
        original_filename: filename,
        file_size_bytes: buffer.length,
        mimetype: part.mimetype,
      },
    });
    await newDoc.save();

    try {
      // 4. Forward to Python RAG Engine for full ingestion: Parse -> Chunk -> Embed -> Index
      const processResult = await ragEngineClient.processAndIndex(buffer, filename, documentId, {
        sourceType,
      });

      // 5. Update MongoDB document status
      newDoc.status = "completed";
      newDoc.total_chunks = processResult.total_chunks;
      newDoc.total_tokens = processResult.total_tokens;
      await newDoc.save();

      return reply.status(201).send({
        status: "success",
        is_duplicate: false,
        message: "Document parsed, chunked, embedded, and indexed in Qdrant successfully.",
        document: {
          id: newDoc.id,
          title: newDoc.title,
          source_type: newDoc.source_type,
          file_hash: newDoc.file_hash,
          total_chunks: newDoc.total_chunks,
          total_tokens: newDoc.total_tokens,
          status: newDoc.status,
          createdAt: newDoc.createdAt,
        },
        collection_name: processResult.collection_name,
      });
    } catch (err: unknown) {
      newDoc.status = "failed";
      await newDoc.save();
      logger.error(`[DocumentsRoute] Processing failed for doc ${documentId}: ${err}`);
      const errorMessage = err instanceof Error ? err.message : String(err);
      return reply.status(502).send({
        error: "RAG Engine Error",
        message: `Failed to process document: ${errorMessage}`,
        document_id: documentId,
      });
    }
  });

  /**
   * GET /api/v1/documents
   * Lists ingested documents.
   */
  server.get("/documents", { preHandler: requireAuth }, async () => {
    const docs = await DocumentModel.find().sort({ createdAt: -1 }).limit(50).exec();
    return {
      status: "success",
      total: docs.length,
      documents: docs.map((d) => ({
        id: d.id,
        title: d.title,
        source_type: d.source_type,
        file_hash: d.file_hash,
        total_chunks: d.total_chunks,
        total_tokens: d.total_tokens,
        status: d.status,
        createdAt: d.createdAt,
      })),
    };
  });

  /**
   * DELETE /api/v1/documents/:id
   * Purges document record from MongoDB and purges vector chunks from Qdrant.
   */
  server.delete("/documents/:id", { preHandler: [requireAuth, requireRole("admin")] }, async (req, reply) => {
    const { id } = req.params as { id: string };
    const doc = await DocumentModel.findOne({ id }).exec();

    if (!doc) {
      return reply.status(404).send({
        error: "Not Found",
        message: `Document with id '${id}' not found.`,
      });
    }

    try {
      // Purge vectors from Qdrant
      await ragEngineClient.deleteVectors(id);

      // Remove from MongoDB
      await DocumentModel.deleteOne({ id }).exec();

      logger.info(`[DocumentsRoute] Completely deleted doc '${id}' from MongoDB and Qdrant.`);
      return reply.status(200).send({
        status: "success",
        message: `Document '${id}' and its vector embeddings deleted successfully.`,
        document_id: id,
      });
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      logger.error(`[DocumentsRoute] Error deleting document '${id}': ${errorMessage}`);
      return reply.status(500).send({
        error: "Deletion Error",
        message: `Failed to purge document: ${errorMessage}`,
        document_id: id,
      });
    }
  });
};

export default documentsRoute;
