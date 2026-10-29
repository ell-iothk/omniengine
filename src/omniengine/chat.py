"""`omniengine chat`: talk to the served model in the terminal, the quickest way to demo it.

Each answer streams in as the model writes it. The conversation is kept, so follow-up questions
work; the model's thinking is hidden unless --show-thinking is given. Ctrl+C stops an answer
while it streams; /exit, Ctrl+D or Ctrl+C at the prompt leaves the chat.
"""

import sys
from collections.abc import Callable
from typing import TextIO

import openai
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from omniengine.settings import ServerSettings
from omniengine.smoke import make_client

EXIT_COMMAND = "/exit"

# ANSI codes for dim text: thinking is shown fainter than the answer in a real terminal.
DIM, RESET = "\033[2m", "\033[0m"


def stream_reply(
    client: OpenAI,
    settings: ServerSettings,
    messages: list[ChatCompletionMessageParam],
    show_thinking: bool,
    out: TextIO,
) -> str:
    """Send the conversation, print the answer while it streams, and return the answer text."""
    stream = client.chat.completions.create(model=settings.model, messages=messages, stream=True)
    dim = out.isatty()  # colour codes only for a real terminal, never in files or tests
    answer = ""
    thought = False  # whether thinking was printed, so the answer starts on its own line
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        # vLLM's reasoning parser sends thinking in an extra "reasoning" field of each delta.
        thinking = getattr(delta, "reasoning", None)
        if thinking and show_thinking:
            out.write(f"{DIM}{thinking}{RESET}" if dim else thinking)
            thought = True
        if delta.content:
            # Qwen3 starts its answer with blank lines after the thinking; drop them.
            text = delta.content if answer else delta.content.lstrip()
            if text and not answer and thought:
                out.write("\n")
            answer += text
            out.write(text)
        out.flush()  # show each piece now, not when the buffer happens to fill
    out.write("\n")
    return answer


def run(
    settings: ServerSettings,
    show_thinking: bool = False,
    read: Callable[[str], str] = input,
    out: TextIO = sys.stdout,
) -> int:
    """Run the chat loop until the user leaves; returns the exit code (always 0)."""
    client = make_client(settings)
    messages: list[ChatCompletionMessageParam] = []
    out.write(f"Chatting with {settings.model} at {settings.base_url}; {EXIT_COMMAND} leaves.\n")
    while True:
        try:
            question = read("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            # Ctrl+D or Ctrl+C: leave cleanly instead of printing a traceback.
            out.write("\n")
            return 0
        if question == EXIT_COMMAND:
            return 0
        if not question:
            continue
        messages.append({"role": "user", "content": question})
        out.write(f"{settings.model}> ")
        try:
            answer = stream_reply(client, settings, messages, show_thinking, out)
        except openai.OpenAIError as error:
            # Server down or context full: say so, forget the question, keep the chat open.
            out.write(f"\nrequest failed: {error}\n")
            messages.pop()
            continue
        except KeyboardInterrupt:
            # Ctrl+C while an answer streams stops that answer, not the whole chat.
            out.write("\n(stopped)\n")
            messages.pop()
            continue
        # Only the answer goes back into the history; Qwen3 is meant to see past turns without
        # their thinking.
        messages.append({"role": "assistant", "content": answer})
