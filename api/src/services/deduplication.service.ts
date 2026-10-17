/**
 * api/src/services/deduplication.service.ts
 * Computes SHA-256 hash and checks MongoDB for duplicate documents.
 * Ref: ARCHITECTURE.md §2.2 Phase A & §4.1
 */

import { createHash } from "node:crypto";
import { DocumentModel, IDocument } from "../models/document.model.js";
import { logger } from "../config/logger.js";

export class DeduplicationService {
  /**
   * Computes the SHA-256 hash of a file buffer.
   *
   * @param buffer Raw file bytes
   * @returns 64-character hexadecimal SHA-256 string
   */
  public computeFileHash(buffer: Buffer): string {
    return createHash("sha256").update(buffer).digest("hex");
  }

  /**
   * Checks MongoDB for an existing document with the identical SHA-256 hash.
   *
   * @param fileHash 64-character SHA-256 string
   * @returns Existing document if found, otherwise null
   */
  public async findDuplicate(fileHash: string): Promise<IDocument | null> {
    try {
      const existingDoc = await DocumentModel.findOne({ file_hash: fileHash }).exec();
      if (existingDoc) {
        logger.info(
          `[Deduplication] Match found for hash ${fileHash.substring(0, 8)}... -> doc id: ${existingDoc.id}`
        );
      }
      return existingDoc;
    } catch (error) {
      logger.error(`[Deduplication] Error querying MongoDB for file_hash: ${error}`);
      throw error;
    }
  }
}

export const deduplicationService = new DeduplicationService();
