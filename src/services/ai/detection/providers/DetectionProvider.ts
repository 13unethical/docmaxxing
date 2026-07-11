import type { DetectionResult } from "../../../../../types/ai";

export interface DetectionProvider {
  detect(text: string): Promise<DetectionResult>;
}
