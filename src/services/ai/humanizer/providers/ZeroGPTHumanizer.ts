import { ZeroGPTClient } from "../../../../../lib/api/zerogpt/client";
import type { HumanizerProvider } from "./HumanizerProvider";
import type { HumanizedResult } from "../../../../../types/ai";
import { ProviderError } from "../../../detection/providers/ZeroGPTProvider";

type JsonObject = Record<string, unknown>;

export class ZeroGPTHumanizer implements HumanizerProvider {
  private readonly client: ZeroGPTClient;

  constructor(client: ZeroGPTClient = new ZeroGPTClient()) {
    this.client = client;
  }

  async humanize(text: string): Promise<HumanizedResult> {
    const raw = await this.client.humanize({ text });
    return mapHumanizerResponse(raw, text);
  }
}

function mapHumanizerResponse(raw: unknown, originalText: string): HumanizedResult {
  if (!isObject(raw)) {
    throw new ProviderError(
      "INVALID_RESPONSE",
      "ZeroGPT humanizer response is not an object",
      "zerogpt",
      raw,
    );
  }

  const humanizedText =
    readString(raw, ["text", "humanizedText", "humanized_text", "result", "output"]) ?? null;
  if (!humanizedText) {
    throw new ProviderError(
      "INVALID_TEXT",
      "ZeroGPT humanizer response does not contain humanized text",
      "zerogpt",
      raw,
    );
  }

  const originalWords =
    readNumber(raw, ["originalWords", "original_words", "input_words"]) ??
    wordCount(originalText);
  const humanizedWords =
    readNumber(raw, ["humanizedWords", "humanized_words", "output_words"]) ??
    wordCount(humanizedText);
  const processingTime =
    readNumber(raw, ["processingTime", "processing_time", "latency_ms", "duration_ms"]) ?? 0;

  return {
    provider: "zerogpt",
    text: humanizedText,
    originalWords,
    humanizedWords,
    processingTime,
    raw,
  };
}

function wordCount(value: string): number {
  const chunks = value.trim().split(/\s+/).filter(Boolean);
  return chunks.length;
}

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
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
