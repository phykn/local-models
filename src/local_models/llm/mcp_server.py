import tomllib
from contextlib import suppress

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .backends import BackendError, OpenAIBackend
from .registry import load_registry

READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}

mcp = FastMCP("llm-local", instructions=(
    "A local LLM (Qwen) on this Mac. Use ask to hand it self-contained text work: drafting, rewriting, translating, "
    "summarizing, or a second opinion. It sees only the prompt and system text you pass, not this conversation or any "
    "files, so include everything it needs. It is much slower than you; keep prompts focused and leave think off "
    "unless the task needs step-by-step reasoning."))

reg = load_registry()


def registry():
    global reg
    # LOCAL-MODELS.app can change a port in llm.toml while this server runs; keep the last good one if it is broken
    with suppress(OSError, tomllib.TOMLDecodeError, KeyError, TypeError):
        reg = load_registry(reg.path)
    return reg


@mcp.tool(annotations=READ_ONLY)
async def list_models() -> dict:
    """The registered local models, which one is the default, and whether each is running (with its start command if not)."""
    reg = registry()
    models = []
    for spec in reg.models.values():
        info = await OpenAIBackend(spec).info()
        models.append({"name": spec.name, "description": spec.description, "default": spec.name == reg.default,
                       "running": info is not None, "url": f"http://127.0.0.1:{spec.port}/v1",
                       **({} if info else {"start": f"llmctl start {spec.name}"})})
    return {"models": models}


@mcp.tool(annotations=READ_ONLY)
async def ask(prompt: str, system: str | None = None, model: str | None = None, think: bool = False,
              max_tokens: int = 2048) -> dict:
    """Send one prompt to a local model and return its answer text.

    system: optional system prompt.
    model: a name from list_models; omit for the default.
    think: let the model reason before answering. Better on hard problems, but often several times slower;
      the reasoning itself is not returned.
    max_tokens: upper bound on generated tokens, reasoning included. finish_reason "length" means the answer was cut off.
    """
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    try:
        out = await OpenAIBackend(registry().get(model)).chat(messages, think=think, max_tokens=max_tokens)
    except (KeyError, BackendError) as e:
        raise ToolError(str(e.args[0]) if e.args else str(e))
    return {k: out[k] for k in ("model", "text", "finish_reason", "usage")}


def main():
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
