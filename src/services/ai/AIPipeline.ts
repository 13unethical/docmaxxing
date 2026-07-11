import { AIServiceFactory, type AIProviderName } from "./AIServiceFactory";
import type { DetectionProvider } from "./detection/providers/DetectionProvider";
import type { HumanizerProvider } from "./humanizer/providers/HumanizerProvider";
import type { DetectionResult } from "../../types/ai";

export interface AIPipelineOutput {
  originalDetection: DetectionResult;
  humanizedText: string;
  finalDetection: DetectionResult;
  improved: boolean;
}

export type AIPipelineStep =
  | "provider-setup"
  | "detection"
  | "humanizer"
  | "final-detection";

export interface AIPipelineError {
  message: string;
  step: AIPipelineStep;
}

export type AIPipelineResult =
  | { success: true; data: AIPipelineOutput }
  | { success: false; error: AIPipelineError };

export class AIPipeline {
  private readonly providerName?: AIProviderName;

  constructor(providerName?: AIProviderName) {
    this.providerName = providerName;
  }

  async process(text: string): Promise<AIPipelineResult> {
    const trimmed = text.trim();
    if (!trimmed) {
      return {
        success: false,
        error: {
          message: "Input text is empty",
          step: "detection",
        },
      };
    }

    let detection: DetectionProvider;
    let humanizer: HumanizerProvider;

    try {
      detection = AIServiceFactory.createDetectionProvider(this.providerName);
      humanizer = AIServiceFactory.createHumanizerProvider(this.providerName);
    } catch (err) {
      return {
        success: false,
        error: {
          message: formatProviderSetupError(err),
          step: "provider-setup",
        },
      };
    }

    let originalDetection: DetectionResult;
    try {
      originalDetection = await detection.detect(trimmed);
    } catch (err) {
      return {
        success: false,
        error: {
          message: formatStepError("Detection failed", err),
          step: "detection",
        },
      };
    }

    let humanizedText: string;
    try {
      const humanized = await humanizer.humanize(trimmed);
      humanizedText = humanized.text.trim();
      if (!humanizedText) {
        return {
          success: false,
          error: {
            message: "Humanizer returned empty text",
            step: "humanizer",
          },
        };
      }
    } catch (err) {
      return {
        success: false,
        error: {
          message: formatHumanizerError(err),
          step: "humanizer",
        },
      };
    }

    let finalDetection: DetectionResult;
    try {
      finalDetection = await detection.detect(humanizedText);
    } catch (err) {
      return {
        success: false,
        error: {
          message: formatStepError("Final detection failed", err),
          step: "final-detection",
        },
      };
    }

    return {
      success: true,
      data: {
        originalDetection,
        humanizedText,
        finalDetection,
        improved: finalDetection.aiScore < originalDetection.aiScore,
      },
    };
  }
}

function formatProviderSetupError(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err);
  if (/humanizer/i.test(message) || /not implemented/i.test(message)) {
    return `Humanizer provider is unavailable: ${message}`;
  }
  return `AI provider setup failed: ${message}`;
}

function formatHumanizerError(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err);
  return `Humanizer is unavailable or failed: ${message}`;
}

function formatStepError(prefix: string, err: unknown): string {
  const message = err instanceof Error ? err.message : String(err);
  return `${prefix}: ${message}`;
}
