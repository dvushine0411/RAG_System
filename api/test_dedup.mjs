/**
 * test_dedup.mjs
 * Test SHA-256 deduplication hashing and consistency.
 */

import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

function computeHash(buf) {
  return createHash("sha256").update(buf).digest("hex");
}

const txtBuffer = readFileSync("../test_docs/sample.txt");
const mdBuffer = readFileSync("../test_docs/sample.md");

const hash1 = computeHash(txtBuffer);
const hash2 = computeHash(txtBuffer);
const hashMd = computeHash(mdBuffer);

console.log("=== Node.js Deduplication Unit Test ===");
console.log(`Sample.txt Hash 1: ${hash1}`);
console.log(`Sample.txt Hash 2: ${hash2}`);
console.log(`Sample.md Hash:    ${hashMd}`);

if (hash1 === hash2) {
  console.log("✅ PASS: Deterministic hashing confirmed (hash1 === hash2).");
} else {
  console.error("❌ FAIL: Hash mismatch!");
  process.exit(1);
}

if (hash1 !== hashMd) {
  console.log("✅ PASS: Different files produce distinct hashes.");
} else {
  console.error("❌ FAIL: Hash collision!");
  process.exit(1);
}

console.log("✅ All Deduplication hash checks passed!");
