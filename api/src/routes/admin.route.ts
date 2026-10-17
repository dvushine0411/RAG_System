/**
 * System Role: Admin-only monitoring endpoint aggregating query latency and token usage from query_logs.
 * Inputs: GET /api/v1/admin/metrics?hours=<1..2160> (default 24); Bearer access token with role "admin".
 * Outputs: { window_hours, totals, latency_ms {p50,p95,p99,avg,max}, ttft_ms {...}, tokens {...}, slowest[] }.
 * Note: uses MongoDB 7.0 $percentile (approximate) inside $group.
 */

import type { FastifyInstance, FastifyPluginAsync } from "fastify";
import type { PipelineStage } from "mongoose";
import { z } from "zod";
import { requireAuth, requireRole } from "../middlewares/auth.middleware.js";
import { QueryLogModel } from "../models/query-log.model.js";

const MetricsQuerySchema = z.object({
  hours: z.coerce.number().int().min(1).max(2160).default(24),
});

const pct = (field: string) => ({ $percentile: { input: field, p: [0.5, 0.95, 0.99], method: "approximate" } });
const round = (v: unknown) => (typeof v === "number" ? Math.round(v) : null);

function summarize(p: unknown, avg: unknown, max: unknown) {
  const arr = Array.isArray(p) ? p : [];
  return { p50: round(arr[0]), p95: round(arr[1]), p99: round(arr[2]), avg: round(avg), max: round(max) };
}

export const adminRoute: FastifyPluginAsync = async (server: FastifyInstance) => {
  server.get("/metrics", { preHandler: [requireAuth, requireRole("admin")] }, async (req, reply) => {
    const parsed = MetricsQuerySchema.safeParse(req.query);
    if (!parsed.success) {
      return reply.status(400).send({ error: "VALIDATION_FAILED", details: parsed.error.flatten() });
    }
    const since = new Date(Date.now() - parsed.data.hours * 3600 * 1000);
    const match = { created_at: { $gte: since } };

    // Cast: mongoose 8.7 typings predate MongoDB 7.0's $percentile accumulator.
    const [stats] = await QueryLogModel.aggregate([
      { $match: match },
      {
        $group: {
          _id: null,
          total: { $sum: 1 },
          errors: { $sum: { $cond: [{ $eq: ["$status", "error"] }, 1, 0] } },
          aborted: { $sum: { $cond: [{ $eq: ["$status", "aborted"] }, 1, 0] } },
          no_citation: { $sum: { $cond: [{ $eq: ["$citations_count", 0] }, 1, 0] } },
          latency_p: pct("$latency_ms"),
          latency_avg: { $avg: "$latency_ms" },
          latency_max: { $max: "$latency_ms" },
          ttft_p: pct("$ttft_ms"),
          ttft_avg: { $avg: "$ttft_ms" },
          ttft_max: { $max: "$ttft_ms" },
          prompt_avg: { $avg: "$token_usage.prompt_tokens" },
          completion_avg: { $avg: "$token_usage.completion_tokens" },
          total_tokens: { $sum: "$token_usage.total_tokens" },
          citations_avg: { $avg: "$citations_count" },
        },
      },
    ] as unknown as PipelineStage[]).exec();

    const slowest = await QueryLogModel.find(match, {
      _id: 0,
      user_query: 1,
      latency_ms: 1,
      ttft_ms: 1,
      status: 1,
      endpoint: 1,
      created_at: 1,
    })
      .sort({ latency_ms: -1 })
      .limit(5)
      .lean()
      .exec();

    if (!stats) {
      return { window_hours: parsed.data.hours, totals: { queries: 0 }, slowest: [] };
    }

    return {
      window_hours: parsed.data.hours,
      totals: {
        queries: stats.total,
        errors: stats.errors,
        aborted: stats.aborted,
        error_rate: stats.total ? Number((stats.errors / stats.total).toFixed(4)) : 0,
        no_citation_rate: stats.total ? Number((stats.no_citation / stats.total).toFixed(4)) : 0,
      },
      latency_ms: summarize(stats.latency_p, stats.latency_avg, stats.latency_max),
      ttft_ms: summarize(stats.ttft_p, stats.ttft_avg, stats.ttft_max),
      tokens: {
        prompt_avg: round(stats.prompt_avg),
        completion_avg: round(stats.completion_avg),
        total: stats.total_tokens ?? 0,
      },
      citations_avg: stats.citations_avg != null ? Number(stats.citations_avg.toFixed(2)) : null,
      slowest,
    };
  });
};
