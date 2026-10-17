/**
 * System Role: Mongoose model for registered user accounts.
 * Inputs: Account data from auth.service (email, name, bcrypt password hash, role).
 * Outputs: `users` collection documents; toPublicUser() strips the password hash for API responses.
 * Ref: ARCHITECTURE.md §4.4 users collection
 */

import mongoose, { Schema, Document } from "mongoose";

export type UserRole = "user" | "admin";

export interface IUser extends Document {
  id: string;
  email: string;
  name: string;
  password_hash: string;
  role: UserRole;
  last_login_at?: Date;
  createdAt: Date;
  updatedAt: Date;
}

export interface PublicUser {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  createdAt: Date;
}

const UserSchema = new Schema<IUser>(
  {
    id: { type: String, required: true, unique: true },
    email: { type: String, required: true, unique: true, lowercase: true, trim: true },
    name: { type: String, required: true, trim: true },
    password_hash: { type: String, required: true },
    role: { type: String, enum: ["user", "admin"], default: "user", index: true },
    last_login_at: { type: Date },
  },
  { timestamps: true }
);

export const UserModel = mongoose.models.User || mongoose.model<IUser>("User", UserSchema);

export function toPublicUser(user: IUser): PublicUser {
  return { id: user.id, email: user.email, name: user.name, role: user.role, createdAt: user.createdAt };
}
