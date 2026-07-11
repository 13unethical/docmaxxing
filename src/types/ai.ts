export interface ParagraphScore {
  paragraphId: string;
  score: number;
  passed: boolean;
}

export interface DetectionResult {
  provider: string;
  aiScore: number;
  passed: boolean;
  paragraphs: ParagraphScore[];
  raw: unknown;
}

export interface HumanizedResult {
  provider: string;
  text: string;
  originalWords: number;
  humanizedWords: number;
  processingTime: number;
  raw: unknown;
}
