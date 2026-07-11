export interface ZeroGPTConfig {
  baseUrl: string;
  apiKey: string;
  timeout: number;
}

const DEFAULT_BASE_URL = "https://api.zerogpt.com";
const DEFAULT_TIMEOUT_MS = 15000;

export function getZeroGPTConfig(): ZeroGPTConfig {
  const apiKey = process.env.ZEROGPT_API_KEY || "";

  return {
    baseUrl: process.env.ZEROGPT_BASE_URL || DEFAULT_BASE_URL,
    apiKey,
    timeout: Number(process.env.ZEROGPT_TIMEOUT_MS || DEFAULT_TIMEOUT_MS),
  };
}
