/**
 * System Role: Mongoose model tracking issued refresh tokens for rotation, revocation and reuse detection.
 * Inputs: Token metadata from token.service (jti, user id, SHA-256 of the raw token, expiry).
 * Outputs: `refresh_tokens` collection; expired rows are purged automatically by a TTL index.
 * Ref: ARCHITECTURE.md §4.5 refresh_tokens collection
 */

import mongoose, { Schema, Document } from "mongoose";

export interface IRefreshToken extends Document {
  jti: string;
  user_id: string;
  token_hash: string; // SHA-256 hex — the raw token is never stored
  expires_at: Date;
  revoked_at?: Date;
  replaced_by?: string; // jti of the token issued when this one was rotated
  user_agent?: string;
  createdAt: Date;
}

const RefreshTokenSchema = new Schema<IRefreshToken>(
  {
    jti: { type: String, required: true, unique: true },
    user_id: { type: String, required: true, index: true },
    token_hash: { type: String, required: true },
    expires_at: { type: Date, required: true },
    revoked_at: { type: Date },
    replaced_by: { type: String },
    user_agent: { type: String },
  },
  { timestamps: { createdAt: true, updatedAt: false }, collection: "refresh_tokens" }
);

// MongoDB deletes the row once expires_at has passed
RefreshTokenSchema.index({ expires_at: 1 }, { expireAfterSeconds: 0 });

export const RefreshTokenModel =
  mongoose.models.RefreshToken || mongoose.model<IRefreshToken>("RefreshToken", RefreshTokenSchema);
