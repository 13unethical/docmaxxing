import type { DetectionProvider } from "./detection/providers/DetectionProvider";
import type { HumanizerProvider } from "./humanizer/providers/HumanizerProvider";
import { ZeroGPTProvider } from "./detection/providers/ZeroGPTProvider";
import { ZeroGPTHumanizer } from "./humanizer/providers/ZeroGPTHumanizer";

export type AIProviderName = "zerogpt" | "turnitin" | "mock";

const SUPPORTED_PROVIDERS: readonly AIProviderName[] = ["zerogpt", "turnitin", "mock"];

function resolveProviderName(explicit?: AIProviderName): AIProviderName {
  if (explicit) {
    return explicit;
  }

  const fromEnv = (process.env.AI_PROVIDER || "zerogpt").trim().toLowerCase();
  if (SUPPORTED_PROVIDERS.includes(fromEnv as AIProviderName)) {
    return fromEnv as AIProviderName;
  }

  throw new Error(
    `Unsupported AI_PROVIDER "${fromEnv}". Expected one of: ${SUPPORTED_PROVIDERS.join(", ")}`,
  );
}

export class AIServiceFactory {
  static getProviderName(provider?: AIProviderName): AIProviderName {
    return resolveProviderName(provider);
  }

  static createDetectionProvider(provider?: AIProviderName): DetectionProvider {
    switch (resolveProviderName(provider)) {
      case "zerogpt":
        return new ZeroGPTProvider();
      case "turnitin":
        // TODO: return new TurnitinDetectionProvider();
        throw new Error("Turnitin DetectionProvider is not implemented yet");
      case "mock":
        // TODO: return new MockDetectionProvider();
        throw new Error("Mock DetectionProvider is not implemented yet");
    }
  }

  static createHumanizerProvider(provider?: AIProviderName): HumanizerProvider {
    switch (resolveProviderName(provider)) {
      case "zerogpt":
        return new ZeroGPTHumanizer();
      case "turnitin":
        // TODO: return new TurnitinHumanizerProvider();
        throw new Error("Turnitin HumanizerProvider is not implemented yet");
      case "mock":
        // TODO: return new MockHumanizerProvider();
        throw new Error("Mock HumanizerProvider is not implemented yet");
    }
  }

  static createProviders(provider?: AIProviderName): {
    detection: DetectionProvider;
    humanizer: HumanizerProvider;
  } {
    const resolved = resolveProviderName(provider);
    return {
      detection: AIServiceFactory.createDetectionProvider(resolved),
      humanizer: AIServiceFactory.createHumanizerProvider(resolved),
    };
  }
}
