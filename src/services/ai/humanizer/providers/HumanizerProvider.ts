import type { HumanizedResult } from "../../../../../types/ai";

export interface HumanizerProvider {
  humanize(text: string): Promise<HumanizedResult>;
}
