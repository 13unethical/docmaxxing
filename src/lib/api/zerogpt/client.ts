import { getZeroGPTConfig, type ZeroGPTConfig } from "./config";
import type {
  ZeroGPTDetectionRequest,
  ZeroGPTDetectionResponse,
  ZeroGPTHumanizerRequest,
  ZeroGPTHumanizerResponse,
} from "./types";

export class ZeroGPTClient {
  private readonly config: ZeroGPTConfig;

  constructor(config?: Partial<ZeroGPTConfig>) {
    const resolved = getZeroGPTConfig();
    this.config = {
      ...resolved,
      ...config,
    };
  }

  async detect(
    payload: ZeroGPTDetectionRequest,
  ): Promise<ZeroGPTDetectionResponse> {
    // TODO: Confirm final ZeroGPT detection endpoint path.
    return this.request<ZeroGPTDetectionResponse>("/v1/detect", payload);
  }

  async humanize(
    payload: ZeroGPTHumanizerRequest,
  ): Promise<ZeroGPTHumanizerResponse> {
    // TODO: Confirm final ZeroGPT humanizer endpoint path.
    return this.request<ZeroGPTHumanizerResponse>("/v1/humanize", payload);
  }

  private async request<TResponse>(
    path: string,
    body: Record<string, unknown>,
  ): Promise<TResponse> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.config.timeout);

    try {
      const response = await fetch(this.buildUrl(path), {
        method: "POST",
        headers: this.buildHeaders(),
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(
          `ZeroGPT request failed: ${response.status} ${response.statusText} - ${text}`,
        );
      }

      return (await response.json()) as TResponse;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  private buildUrl(path: string): string {
    const base = this.config.baseUrl.replace(/\/+$/, "");
    const suffix = path.startsWith("/") ? path : `/${path}`;
    return `${base}${suffix}`;
  }

  private buildHeaders(): HeadersInit {
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${this.config.apiKey}`,
    };
  }
}
