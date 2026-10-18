from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ..registry import RegistryError
from .backends import BackendError, KevHttpBackend
from .registry import load_registry

READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}
LOW_CONFIDENCE_NOTE = ("Every answer carries probabilities and a confidence in [0, 1]. When low_confidence is true, do not act on "
                       "the answer alone: check it yourself or ask the user.")

mcp = FastMCP("kev", instructions=(
    "Local Kev decision models: fast, calibrated classification of a text without generating any. Use choose for one of "
    "several options, yes_no for a yes/no judgement, score for a level on an ordered scale, decide for several questions "
    "about the same text in one call. The model reads only the text and the question you pass, so put everything it "
    "needs into them. " + LOW_CONFIDENCE_NOTE))

reg = load_registry()


def registry():
    global reg
    reg = reg.reload()   # LOCAL-MODELS.app can change a port in kev.toml while this server runs
    return reg


async def ask(model, text, questions):
    try:
        return await KevHttpBackend(registry().get(model)).decide(text, questions)
    except (RegistryError, BackendError) as e:
        raise ToolError(str(e))


async def ask_one(model, text, question):
    out = await ask(model, text, {"q": question})
    return {"model": out["model"], **out["answers"]["q"], "latency_ms": out["latency_ms"]}


@mcp.tool(annotations=READ_ONLY)
async def list_models() -> dict:
    """The registered decision models, which one is the default, and whether each is running (with its start command if not)."""
    reg = registry()
    models = []
    for spec in reg.models.values():
        info = await KevHttpBackend(spec).info()
        models.append({"name": spec.name, "description": spec.description, "default": spec.name == reg.default,
                       "running": info is not None, "min_confidence": spec.min_confidence,
                       **({"serving": info} if info else {"start": f"kevctl start {spec.name}"})})
    return {"models": models}


@mcp.tool(annotations=READ_ONLY)
async def choose(text: str, question: str, options: dict[str, str | None], model: str | None = None) -> dict:
    """Pick the option that best answers the question about the text.

    options maps each option name to a short description of when it applies (or null). The answer is the option name.
    model: a name from list_models; omit for the default.
    When low_confidence is true, do not act on the answer alone: check it yourself or ask the user.
    """
    return await ask_one(model, text, {"type": "choice", "instructions": question, "criteria": options})


@mcp.tool(annotations=READ_ONLY)
async def yes_no(text: str, question: str, yes_means: str | None = None, no_means: str | None = None,
                 model: str | None = None) -> dict:
    """Answer a yes/no question about the text. answer is true for yes; probability_yes is the calibrated P(yes).

    yes_means / no_means optionally spell out what counts as yes or no.
    model: a name from list_models; omit for the default.
    When low_confidence is true, do not act on the answer alone: check it yourself or ask the user.
    """
    criteria = {k: v for k, v in (("true", yes_means), ("false", no_means)) if v}
    return await ask_one(model, text, {"type": "noul", "instructions": question, **({"criteria": criteria} if criteria else {})})


@mcp.tool(annotations=READ_ONLY)
async def score(text: str, question: str, levels: list[str], model: str | None = None) -> dict:
    """Rate the text on an ordered scale. levels go from lowest to highest, e.g. ["low", "medium", "high"].

    answer is the most likely level; score is the expected level index (0 = first level), useful for ranking.
    model: a name from list_models; omit for the default.
    When low_confidence is true, do not act on the answer alone: check it yourself or ask the user.
    """
    return await ask_one(model, text, {"type": "score", "instructions": question, "criteria": levels})


@mcp.tool(annotations=READ_ONLY)
async def decide(text: str, questions: dict[str, dict], model: str | None = None) -> dict:
    """Ask several questions about the same text in one call (the text is read once).

    questions maps your own id to a question in Kev's /v1/systemone shape:
      {"type": "choice", "instructions": "...", "criteria": {"option": "description or null", ...}}
      {"type": "noul",   "instructions": "...", "criteria": {"true": "...", "false": "..."}}   (criteria optional; noul = yes/no)
      {"type": "score",  "instructions": "...", "criteria": ["lowest level", ..., "highest level"]}
    Returns {model, answers: {id: answer}, latency_ms}.
    model: a name from list_models; omit for the default.
    When low_confidence is true, do not act on the answer alone: check it yourself or ask the user.
    """
    out = await ask(model, text, questions)
    return {k: out[k] for k in ("model", "answers", "latency_ms")}


def main():
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
