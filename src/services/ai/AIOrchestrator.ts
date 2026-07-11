import { AIServiceFactory, type AIProviderName } from "./AIServiceFactory";
import { AIPipeline, type AIPipelineOutput } from "./AIPipeline";

export interface AIReviewSummary {
  improved: boolean;
  originalAiScore: number | null;
  finalAiScore: number | null;
  humanizedText: string | null;
  message: string;
  error?: {
    step: string;
    message: string;
  };
}

export interface AIOrchestratorResult {
  success: boolean;
  provider: AIProviderName;
  pipeline: AIPipelineOutput | null;
  review: AIReviewSummary;
}

export class AIOrchestrator {
  private readonly pipeline: AIPipeline;
  private readonly providerName: AIProviderName;

  constructor(providerName?: AIProviderName) {
    this.providerName = AIServiceFactory.getProviderName(providerName);
    this.pipeline = new AIPipeline(this.providerName);
  }

  async review(text: string): Promise<AIOrchestratorResult> {
    // TODO: Cache — reuse recent review results for identical input text.
    // TODO: Rate limit — throttle provider calls per tenant/session.

    const pipelineResult = await this.pipeline.process(text);

    if (!pipelineResult.success) {
      return {
        success: false,
        provider: this.providerName,
        pipeline: null,
        review: {
          improved: false,
          originalAiScore: null,
          finalAiScore: null,
          humanizedText: null,
          message: pipelineResult.error.message,
          error: {
            step: pipelineResult.error.step,
            message: pipelineResult.error.message,
          },
        },
      };
    }

    const { originalDetection, humanizedText, finalDetection, improved } =
      pipelineResult.data;

    // TODO: Retry Humanizer — re-run humanization when improved === false.
    // TODO: Multiple Humanizers — chain or compare outputs from several providers.
    // TODO: Turnitin fallback — switch detection provider when primary fails.
    // TODO: GPTZero fallback — switch detection provider when primary fails.
    // TODO: Parallel providers — run multiple pipelines and pick the best outcome.

    if (improved) {
      return buildOrchestratorResult({
        provider: this.providerName,
        pipeline: pipelineResult.data,
        message: "AI score improved after humanization",
      });
    }

    return buildOrchestratorResult({
      provider: this.providerName,
      pipeline: pipelineResult.data,
      message: "AI score did not improve after humanization",
    });
  }
}

function buildOrchestratorResult(args: {
  provider: AIProviderName;
  pipeline: AIPipelineOutput;
  message: string;
}): AIOrchestratorResult {
  const { originalDetection, humanizedText, finalDetection, improved } = args.pipeline;

  return {
    success: true,
    provider: args.provider,
    pipeline: args.pipeline,
    review: {
      improved,
      originalAiScore: originalDetection.aiScore,
      finalAiScore: finalDetection.aiScore,
      humanizedText,
      message: args.message,
    },
  };
}
