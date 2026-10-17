/**
 * System Role: MongoDB connection lifecycle manager for the API Gateway (Mongoose).
 * Inputs: MONGO_URI and MONGO_SERVER_SELECTION_TIMEOUT_MS from centralized envConfig.
 * Outputs: An established Mongoose connection on startup; graceful disconnect on shutdown.
 * Ref: ARCHITECTURE.md §5.1 Metadata Store & §5 Centralized Config Principle
 */

import mongoose from "mongoose";
import { envConfig } from "./env.config.js";
import { logger } from "./logger.js";

/**
 * Opens the shared Mongoose connection. Must be awaited before routes touch DocumentModel,
 * otherwise Mongoose buffers queries and they time out.
 */
export async function connectDatabase(): Promise<void> {
  await mongoose.connect(envConfig.MONGO_URI, {
    serverSelectionTimeoutMS: envConfig.MONGO_SERVER_SELECTION_TIMEOUT_MS,
  });
  logger.info("✅ Connected to MongoDB.");
}

/**
 * Closes the shared Mongoose connection.
 */
export async function disconnectDatabase(): Promise<void> {
  await mongoose.disconnect();
  logger.info("🛑 Disconnected from MongoDB.");
}
