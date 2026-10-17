// db/mongo_init/001_init_collections.js
// Script khởi tạo MongoDB collections, indexes, và validation schemas
// Tự động chạy khi container mongodb khởi động lần đầu
// Ref: ARCHITECTURE.md §4 Database Schemas
// Note: chunks (text + payload + vector) live only in Qdrant — no document_chunks collection (§4.2)

// Chuyển sang database dự án
db = db.getSiblingDB(process.env.MONGO_INITDB_DATABASE || "rag_db");

// ─────────────────────────────────────────────────────────────────
// Collection 1: documents
// Tracks raw source files and their processing lifecycle
// ─────────────────────────────────────────────────────────────────
db.createCollection("documents", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["title", "source_type", "file_hash", "status"],
      properties: {
        title: { bsonType: "string", description: "Document title - required" },
        source_type: {
          bsonType: "string",
          enum: ["pdf", "docx", "markdown", "text", "html", "url"],
          description: "Source file type - required"
        },
        source_url: { bsonType: "string" },
        file_hash: {
          bsonType: "string",
          description: "SHA-256 hash for deduplication - required and unique"
        },
        total_chunks: { bsonType: "int", minimum: 0 },
        status: {
          bsonType: "string",
          enum: ["pending", "processing", "completed", "failed"],
          description: "Processing lifecycle status"
        },
        metadata: { bsonType: "object" },
        created_at: { bsonType: "date" },
        updated_at: { bsonType: "date" }
      }
    }
  }
});

// Indexes cho documents
db.documents.createIndex({ file_hash: 1 }, { unique: true, name: "idx_file_hash_unique" });
db.documents.createIndex({ status: 1 }, { name: "idx_status" });
db.documents.createIndex({ created_at: -1 }, { name: "idx_created_at_desc" });

print("✅ Collection 'documents' created with indexes.");

// ─────────────────────────────────────────────────────────────────
// Collection 2: query_logs
// Audit log: queries, retrieved chunks, scores, generated responses
// Ref: ARCHITECTURE.md §4.3
// ─────────────────────────────────────────────────────────────────
db.createCollection("query_logs", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["user_query"],
      properties: {
        user_query: { bsonType: "string" },
        retrieved_chunk_ids: {
          bsonType: "array",
          items: { bsonType: "string" }
        },
        rerank_scores: { bsonType: "object" },
        generated_response: { bsonType: "string" },
        latency_ms: { bsonType: "int" },
        token_usage: { bsonType: "object" },
        feedback_score: {
          bsonType: "int",
          minimum: -1,
          maximum: 1,
          description: "Optional user feedback: -1, 0, +1"
        },
        created_at: { bsonType: "date" }
      }
    }
  }
});

// Indexes cho query_logs
db.query_logs.createIndex({ created_at: -1 }, { name: "idx_query_created_at_desc" });
db.query_logs.createIndex({ feedback_score: 1 }, { sparse: true, name: "idx_feedback_score" });

// TTL index: tự xóa log sau 90 ngày (optional)
db.query_logs.createIndex(
  { created_at: 1 },
  { expireAfterSeconds: 7776000, name: "idx_query_logs_ttl_90d" }
);

print("✅ Collection 'query_logs' created with indexes.");
// ─────────────────────────────────────────────────────────────────
// Collection 3: users
// Registered accounts — password stored only as a bcrypt hash
// Ref: ARCHITECTURE.md §4.4
// ─────────────────────────────────────────────────────────────────
db.createCollection("users", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["id", "email", "name", "password_hash", "role"],
      properties: {
        id: { bsonType: "string" },
        email: { bsonType: "string" },
        name: { bsonType: "string" },
        password_hash: { bsonType: "string", pattern: "^\\$2[aby]\\$", description: "bcrypt hash only" },
        role: { bsonType: "string", enum: ["user", "admin"] },
        last_login_at: { bsonType: "date" }
      }
    }
  }
});
db.users.createIndex({ id: 1 }, { unique: true });
db.users.createIndex({ email: 1 }, { unique: true });
db.users.createIndex({ role: 1 });

print("✅ Collection 'users' created with indexes.");

// ─────────────────────────────────────────────────────────────────
// Collection 4: refresh_tokens
// Issued refresh tokens (SHA-256 hash only) for rotation / revocation / reuse detection
// Ref: ARCHITECTURE.md §4.5
// ─────────────────────────────────────────────────────────────────
db.createCollection("refresh_tokens", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["jti", "user_id", "token_hash", "expires_at"],
      properties: {
        jti: { bsonType: "string" },
        user_id: { bsonType: "string" },
        token_hash: { bsonType: "string", minLength: 64, maxLength: 64 },
        expires_at: { bsonType: "date" },
        revoked_at: { bsonType: "date" },
        replaced_by: { bsonType: "string" },
        user_agent: { bsonType: "string" }
      }
    }
  }
});
db.refresh_tokens.createIndex({ jti: 1 }, { unique: true });
db.refresh_tokens.createIndex({ user_id: 1 });
db.refresh_tokens.createIndex({ expires_at: 1 }, { expireAfterSeconds: 0 });

print("✅ Collection 'refresh_tokens' created with indexes.");
print("🚀 MongoDB initialization complete.");
