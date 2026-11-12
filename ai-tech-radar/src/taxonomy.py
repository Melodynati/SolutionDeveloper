"""Seed taxonomy of AI technologies.

The Bedrock extractor normalises free-text mentions onto these canonical names.
Anything it finds that is NOT in this list is still recorded, flagged is_new=True,
so genuinely new technologies surface as "Emerging" candidates instead of being lost.
Keyword lists double as the deterministic fallback when Bedrock is unavailable.
"""

TAXONOMY = {
    # canonical name: (category, [keywords, lower-case])
    "AI Agents": ("Agentic AI", ["ai agent", "agentic", "autonomous agent", "agent framework", "multi-agent"]),
    "Model Context Protocol (MCP)": ("Agentic AI", ["mcp server", "model context protocol", " mcp "]),
    "Agent-to-Agent (A2A)": ("Agentic AI", ["a2a protocol", "agent2agent", "agent-to-agent"]),
    "Computer Use / Browser Agents": ("Agentic AI", ["computer use", "browser agent", "web agent", "browser automation agent"]),
    "Retrieval-Augmented Generation (RAG)": ("Knowledge & Retrieval", ["rag", "retrieval-augmented", "retrieval augmented"]),
    "GraphRAG / Knowledge Graphs": ("Knowledge & Retrieval", ["graphrag", "knowledge graph"]),
    "Vector Databases": ("Knowledge & Retrieval", ["vector database", "vector db", "vector search", "embedding store"]),
    "Embedding Models": ("Knowledge & Retrieval", ["embedding model", "text embedding", "embeddings"]),
    "Reasoning Models": ("Foundation Models", ["reasoning model", "chain-of-thought", "test-time compute", "thinking model"]),
    "Small Language Models (SLM)": ("Foundation Models", ["small language model", "slm", "on-device llm", "edge llm"]),
    "Mixture of Experts (MoE)": ("Foundation Models", ["mixture of experts", "moe"]),
    "Multimodal Models": ("Foundation Models", ["multimodal", "vision-language", "vlm", "omni model"]),
    "Diffusion / Image Generation": ("Generative Media", ["diffusion", "text-to-image", "image generation"]),
    "Video Generation": ("Generative Media", ["text-to-video", "video generation", "video model"]),
    "Speech / Voice AI": ("Generative Media", ["text-to-speech", "tts", "speech recognition", "asr", "voice agent", "speech-to-speech"]),
    "World Models": ("Foundation Models", ["world model"]),
    "Fine-tuning (LoRA / PEFT)": ("Model Customisation", ["lora", "qlora", "peft", "fine-tuning", "fine tuning", "finetune"]),
    "Reinforcement Learning (RLHF / RLVR)": ("Model Customisation", ["rlhf", "rlvr", "reinforcement learning", "grpo", "dpo"]),
    "Model Distillation": ("Model Customisation", ["distillation", "distilled"]),
    "Quantization": ("Inference & Efficiency", ["quantization", "quantized", "gguf", "int4", "fp8", "awq"]),
    "LLM Inference Engines": ("Inference & Efficiency", ["vllm", "sglang", "tensorrt-llm", "llama.cpp", "inference engine", "speculative decoding"]),
    "AI Coding Assistants": ("AI for Developers", ["coding agent", "code assistant", "ai coding", "code generation", "vibe coding"]),
    "LLM Evaluation & Observability": ("LLMOps", ["llm eval", "evals", "benchmark", "llm observability", "tracing"]),
    "AI Guardrails & Safety": ("AI Security & Governance", ["guardrail", "jailbreak", "prompt injection", "red team", "ai safety"]),
    "AI Governance & Regulation": ("AI Security & Governance", ["ai act", "ai regulation", "ai governance", "ai policy"]),
    "AI Security (AI-SPM)": ("AI Security & Governance", ["ai security", "model security", "llm security", "ai-spm"]),
    "Edge / On-device AI": ("Infrastructure", ["on-device", "edge ai", "npu"]),
    "AI Accelerators / GPUs": ("Infrastructure", ["gpu", "tpu", "trainium", "inferentia", "accelerator", "h100", "b200", "gb200"]),
    "Synthetic Data": ("Data", ["synthetic data"]),
    "Document AI / OCR": ("Data", ["ocr", "document ai", "document understanding", "pdf parsing"]),
    "Robotics / Embodied AI": ("Physical AI", ["robotics", "embodied", "humanoid", "vla model", "vision-language-action"]),
    "AI for Science": ("Applied AI", ["protein", "drug discovery", "materials discovery", "ai for science", "weather model"]),
    "Thai-language LLMs": ("Foundation Models", ["thai llm", "thai language model", "openthaigpt", "typhoon llm"]),
    "AI in Capital Markets": ("Applied AI", ["algorithmic trading", "ai trading", "fintech ai", "robo-advisor"]),
}

CATEGORIES = sorted({c for c, _ in TAXONOMY.values()})


def canonical_names():
    return list(TAXONOMY.keys())


def keyword_match(text: str):
    """Deterministic fallback extractor. Returns list of canonical names found in text."""
    t = f" {text.lower()} "
    hits = []
    for name, (_, kws) in TAXONOMY.items():
        if any(k in t for k in kws):
            hits.append(name)
    return hits


def category_of(name: str, default: str = "Emerging / Uncategorised") -> str:
    return TAXONOMY.get(name, (default, []))[0]
