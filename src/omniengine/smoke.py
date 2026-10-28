"""`omniengine smoke`: check the server the way an agent uses it.

Every check returns a CheckResult instead of raising, so one failure never hides the others
and the command always prints a full report. Exit code 0 means every check passed.
"""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

import openai
from openai import OpenAI
from openai.types.chat import ChatCompletionFunctionToolParam, ChatCompletionMessageFunctionToolCall
from openai.types.shared_params import ResponseFormatJSONSchema

from omniengine.settings import ServerSettings

# Seconds to wait for one answer before the check counts as failed.
TIMEOUT_SECONDS = 30.0

# Room for Qwen3's thinking before the answer; too small and the answer is cut off.
CHAT_MAX_TOKENS = 1024

# The kind of tool analyst-agent gives the model: a JSON schema the arguments must follow.
RUN_SQL_TOOL: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": "run_sql",
        "description": "Run a read-only SQL query and return the rows",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}

# Asks for JSON that follows this schema; vLLM then only lets the model write matching tokens.
SUM_FORMAT: ResponseFormatJSONSchema = {
    "type": "json_schema",
    "json_schema": {
        "name": "sum",
        "schema": {
            "type": "object",
            "properties": {"answer": {"type": "integer"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one check, with a one-line explanation for the report."""

    name: str
    passed: bool
    detail: str


def make_client(settings: ServerSettings) -> OpenAI:
    """The official OpenAI client, configured the way an agent would configure it."""
    return OpenAI(
        base_url=settings.base_url,
        # The library refuses to start without a key. vLLM ignores the header when it checks
        # no key, so a placeholder is enough; agents do the same.
        api_key=settings.api_key or "no-key",
        # Report a failure at once instead of retrying it silently (the default is 2 retries).
        max_retries=0,
        timeout=TIMEOUT_SECONDS,
    )


def check_health(settings: ServerSettings) -> CheckResult:
    """GET /health, the same endpoint the compose healthcheck uses; vLLM serves it outside /v1."""
    url = settings.base_url.removesuffix("/v1") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        # The server answered, but not with 2xx (vLLM returns 503 while it is not ready).
        status = error.code
        error.close()
    except OSError as error:
        # No answer at all: connection refused, unknown host or timeout.
        return CheckResult("health", False, f"GET {url} failed: {error}")
    return CheckResult("health", status == 200, f"GET {url} returned {status}")


def check_models(client: OpenAI, settings: ServerSettings) -> CheckResult:
    """GET /v1/models: the alias must be listed, because agents send it as "model"."""
    try:
        served = [model.id for model in client.models.list()]
    except openai.OpenAIError as error:
        return CheckResult("models", False, f"listing models failed: {error}")
    if settings.model in served:
        return CheckResult("models", True, f"{settings.model} is served")
    listed = ", ".join(served) or "nothing"
    return CheckResult("models", False, f"{settings.model} is not served; served: {listed}")


def check_chat(client: OpenAI, settings: ServerSettings) -> CheckResult:
    """POST /v1/chat/completions: a question with one right answer, asked like an agent asks."""
    started = time.monotonic()
    try:
        completion = client.chat.completions.create(
            model=settings.model,
            messages=[{"role": "user", "content": "What is 2 + 3? Answer with the number only."}],
            max_tokens=CHAT_MAX_TOKENS,
        )
    except openai.OpenAIError as error:
        return CheckResult("chat", False, f"request failed: {error}")
    seconds = time.monotonic() - started
    choice = completion.choices[0]
    content = (choice.message.content or "").strip()
    if choice.finish_reason != "stop":
        # "length" means max_tokens ran out before the answer was finished.
        return CheckResult("chat", False, f"finish_reason is {choice.finish_reason!r}, not 'stop'")
    if "<think>" in content or "</think>" in content:
        # Thinking leaked into the answer: the reasoning parser is missing or wrong.
        return CheckResult("chat", False, f"thinking leaked into the answer: {content[:60]!r}")
    if "5" not in content:
        return CheckResult("chat", False, f"expected 5, got {content[:60]!r}")
    tokens = completion.usage.completion_tokens if completion.usage else "?"
    return CheckResult("chat", True, f"answered {content!r} in {seconds:.1f} s ({tokens} tokens)")


def check_tools(client: OpenAI, settings: ServerSettings) -> CheckResult:
    """A question only a tool can answer: the model must call run_sql with valid JSON arguments."""
    try:
        completion = client.chat.completions.create(
            model=settings.model,
            messages=[{"role": "user", "content": "How many rows does the customers table have?"}],
            tools=[RUN_SQL_TOOL],
            max_tokens=CHAT_MAX_TOKENS,
        )
    except openai.OpenAIError as error:
        return CheckResult("tools", False, f"request failed: {error}")
    choice = completion.choices[0]
    calls = choice.message.tool_calls or []
    if choice.finish_reason != "tool_calls" or not calls:
        # A <tool_call> tag inside the content means the tool-call parser is missing or wrong.
        content = (choice.message.content or "").strip()
        reason = f"no tool call, finish_reason {choice.finish_reason!r}"
        return CheckResult("tools", False, f"{reason}: {content[:60]!r}")
    call = calls[0]
    if not isinstance(call, ChatCompletionMessageFunctionToolCall):
        return CheckResult("tools", False, f"expected a function call, got type {call.type!r}")
    if call.function.name != "run_sql":
        return CheckResult("tools", False, f"called {call.function.name!r} instead of 'run_sql'")
    # The arguments arrive as a JSON string; an agent must be able to parse them as-is.
    try:
        arguments = json.loads(call.function.arguments)
    except json.JSONDecodeError:
        return CheckResult("tools", False, f"arguments are not JSON: {call.function.arguments!r}")
    query = arguments.get("query") if isinstance(arguments, dict) else None
    if not isinstance(query, str):
        return CheckResult("tools", False, f"no 'query' string in {call.function.arguments!r}")
    return CheckResult("tools", True, f"called run_sql with {query!r}")


def check_structured(client: OpenAI, settings: ServerSettings) -> CheckResult:
    """response_format with a JSON schema: the answer must be JSON that follows the schema."""
    try:
        completion = client.chat.completions.create(
            model=settings.model,
            messages=[{"role": "user", "content": "What is 2 + 3? Reply in JSON."}],
            response_format=SUM_FORMAT,
            max_tokens=CHAT_MAX_TOKENS,
        )
    except openai.OpenAIError as error:
        return CheckResult("json", False, f"request failed: {error}")
    content = (completion.choices[0].message.content or "").strip()
    try:
        answer = json.loads(content)
    except json.JSONDecodeError:
        return CheckResult("json", False, f"content is not JSON: {content[:60]!r}")
    # bool is a subclass of int in Python, so true/false must be ruled out on their own.
    value = answer.get("answer") if isinstance(answer, dict) else None
    if not isinstance(value, int) or isinstance(value, bool):
        return CheckResult("json", False, f"no integer 'answer' in {content[:60]!r}")
        # Re-encode compactly: vLLM may spread the JSON over lines, the report needs one line.
    return CheckResult("json", True, f"returned {json.dumps(answer)}")


def run(settings: ServerSettings) -> int:
    """Run every check, print one line per check, and return the exit code."""
    client = make_client(settings)
    results = [
        check_health(settings),
        check_models(client, settings),
        check_chat(client, settings),
        check_tools(client, settings),
        check_structured(client, settings),
    ]
    for result in results:
        print(f"{'PASS' if result.passed else 'FAIL'}  {result.name:<8} {result.detail}")
    passed = sum(result.passed for result in results)
    print(f"{passed} of {len(results)} checks passed against {settings.base_url}")
    return 0 if passed == len(results) else 1
