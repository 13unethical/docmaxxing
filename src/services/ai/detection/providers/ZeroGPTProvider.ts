import { ZeroGPTClient } from "../../../../../lib/api/zerogpt/client";
import type { DetectionProvider } from "./DetectionProvider";
import type { DetectionResult, ParagraphScore } from "../../../../../types/ai";

type JsonObject = Record<string, unknown>;

export class ProviderError extends Error {
  public readonly code: string;
  public readonly provider: string;
  public readonly raw?: unknown;

  constructor(code: string, message: string, provider: string, raw?: unknown) {
    super(message);
    this.name = "ProviderError";
    this.code = code;
    this.provider = provider;
    this.raw = raw;
  }
}

export class ZeroGPTProvider implements DetectionProvider {
  private readonly client: ZeroGPTClient;

  constructor(client: ZeroGPTClient = new ZeroGPTClient()) {
    this.client = client;
  }

  async detect(text: string): Promise<DetectionResult> {
    const raw = await this.client.detect({ text });
    return mapDetectionResponse(raw);
  }
}

function mapDetectionResponse(raw: unknown): DetectionResult {
  if (!isObject(raw)) {
    throw new ProviderError(
      "INVALID_RESPONSE",
      "ZeroGPT detection response is not an object",
      "zerogpt",
      raw,
    );
  }

  const aiScore =
    readNumber(raw, ["aiScore", "ai_score", "score", "averageScore", "average_score"]) ?? null;
  if (aiScore == null) {
    throw new ProviderError(
      "INVALID_SCORE",
      "ZeroGPT detection response does not contain a valid ai score",
      "zerogpt",
      raw,
    );
  }

  const paragraphs = mapParagraphs(raw);
  const passed =
    readBoolean(raw, ["passed", "is_passed", "result"]) ??
    aiScore <= 15;

  return {
    provider: "zerogpt",
    aiScore,
    passed,
    paragraphs,
    raw,
  };
}

function mapParagraphs(raw: JsonObject): ParagraphScore[] {
  const source =
    readArray(raw, ["paragraphs", "paragraph_scores", "sentence_scores", "scores"]) ?? [];

  return source
    .map((item, idx) => {
      if (!isObject(item)) return null;
      const score = readNumber(item, ["score", "aiScore", "ai_score"]);
      if (score == null) return null;
      const paragraphId =
        readString(item, ["paragraphId", "paragraph_id", "id"]) ?? `p-${idx + 1}`;
      const passed =
        readBoolean(item, ["passed", "is_passed"]) ??
        score <= 15;
      return { paragraphId, score, passed };
    })
    .filter((v): v is ParagraphScore => v !== null);
}

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readArray(obj: JsonObject, keys: string[]): unknown[] | null {
  for (const key of keys) {
    const value = obj[key];
    if (Array.isArray(value)) return value;
  }
  return null;
}

function readString(obj: JsonObject, keys: string[]): string | null {
  for (const key of keys) {
    const value = obj[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

function readNumber(obj: JsonObject, keys: string[]): number | null {
  for (const key of keys) {
    const value = obj[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
      const num = Number(value);
      if (Number.isFinite(num)) return num;
    }
  }
  return null;
}

function readBoolean(obj: JsonObject, keys: string[]): boolean | null {
  for (const key of keys) {
    const value = obj[key];
    if (typeof value === "boolean") return value;
    if (typeof value === "string") {
      const normalized = value.toLowerCase().trim();
      if (normalized === "true" || normalized === "pass" || normalized === "passed") {
        return true;
      }
      if (normalized === "false" || normalized === "fail" || normalized === "failed") {
        return false;
      }
    }
  }
  return null;
}
