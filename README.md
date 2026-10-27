# OmniEngine

[![CI](https://github.com/ell-iothk/omniengine/actions/workflows/ci.yml/badge.svg)](https://github.com/ell-iothk/omniengine/actions/workflows/ci.yml)

**Observable LLM Inference Platform Powered by vLLM for Agentic API Integration**


> **Status: work in progress.** The repository skeleton, tooling and CI are in place.
> The vLLM serving stack is being built next.

OmniEngine runs one local LLM behind an OpenAI-compatible API so that many agents can share it.
Agents only see `LLM_BASE_URL` and a stable model alias; they never need to know which model is serving.
The first consumer is [analyst-agent](https://github.com/ell-iothk/analyst-agent), a text-to-SQL agent with tool calling.

## Planned features

- Reproducible serving with Docker Compose: pinned vLLM image, pinned model revisions,
  Hugging Face cache in a named volume
- Fits a 6 GB GPU: 4-bit (AWQ) models with tuned context length and GPU memory use
- Reliable tool calling with vLLM tool-call parsers and structured outputs
- Health checks and an `omniengine smoke` contract test
- Benchmarks (p50/p95 latency, time to first token, tokens per second, VRAM) and a
  tool-calling eval that picks the default model
- Optional monitoring profile: Prometheus and Grafana on vLLM's `/metrics`

## Requirements

- Linux or WSL2, with Python tooling managed by [uv](https://docs.astral.sh/uv/)
- For serving (coming next): an NVIDIA GPU, Docker Engine and the NVIDIA Container Toolkit

## Development

```bash
make setup   # install dependencies from uv.lock and the pre-commit hook
make check   # lint, type check, tests and every pre-commit hook (the same as CI)
make help    # list every target
```

Tests that need a GPU are marked `gpu` and run locally; CI runs on GitHub without a GPU.

## License

The code in this repository is released under the [MIT License](LICENSE).
Model weights are not part of this repository and keep their own licenses.
