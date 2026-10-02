# -*- coding: utf-8 -*-
"""
Talking to the AI.

One function, ask_model(). Which AI it uses is decided by one setting, so the
rest of the app never needs to know or care.

  CRA_MODEL_MODE = mock       no AI at all. Works with no key. Use this first.
  CRA_MODEL_MODE = openai     OpenAI or Azure OpenAI, using CRA_API_KEY
  CRA_MODEL_MODE = anthropic  Claude, using CRA_API_KEY
  CRA_MODEL_MODE = paste      only the ChatGPT website is allowed. The app
                              writes the prompt to a file, you paste it into
                              ChatGPT, and save the reply into a second file.

Light on purpose:
  - plain HTTP from the standard library, no openai or anthropic package
  - every answer is saved in out/.cache, so the same question twice costs
    nothing the second time
  - the instructions are marked for prompt caching on Anthropic. OpenAI
    caches a repeated opening on its own.
  - cheap default models. The work is short wording, not reasoning.

Nothing in here decides a number. See cra/review.py for the rule that enforces
that, and tests/test_privacy.py for the test that holds it down.
"""
import os
import sys
import json
import hashlib
import urllib.request
import urllib.error


def _load_env(path=".env"):
    """Read KEY=value lines from .env into the environment. No package needed."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

DEFAULT_MODEL = {"openai": "gpt-4.1-mini", "anthropic": "claude-haiku-4-5"}
MAX_TOKENS = int(os.environ.get("CRA_MAX_TOKENS", "1500"))
CACHE_DIR = os.path.join("out", ".cache")

PROMPT_FILE = os.path.join("out", "prompt_to_paste.txt")
ANSWER_FILE = os.path.join("out", "answer_from_chatgpt.txt")

# what the last real call used, for the screen
LAST_USAGE = {}


def _setting(name, default=""):
    return os.environ.get(name, default)


def current_mode():
    return _setting("CRA_MODEL_MODE", "mock").lower()


def model_name(mode):
    return _setting("CRA_MODEL_NAME") or DEFAULT_MODEL.get(mode, "")


def ask_model(system_prompt, user_prompt, mode=None):
    """Send two pieces of text to the AI and get text back."""
    mode = (mode or current_mode()).lower()
    if mode == "mock":
        return _mock(user_prompt)
    if mode == "paste":
        return _paste(system_prompt, user_prompt)
    if mode not in ("openai", "anthropic"):
        raise ValueError("Unknown CRA_MODEL_MODE: %s" % mode)

    key = hashlib.sha256(("%s|%s|%s|%s" % (mode, model_name(mode), system_prompt,
                                           user_prompt)).encode()).hexdigest()
    cached = os.path.join(CACHE_DIR, key + ".txt")
    if os.path.exists(cached):
        LAST_USAGE.clear()
        LAST_USAGE.update({"cached": True})
        with open(cached, encoding="utf-8") as fh:
            return fh.read()

    text = (_openai if mode == "openai" else _anthropic)(system_prompt,
                                                          user_prompt)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cached, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text


def _post(url, headers, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError("%s %s" % (e.code, e.read().decode()[:300]))


def _openai(system_prompt, user_prompt):
    base = (_setting("CRA_API_BASE") or "https://api.openai.com/v1").rstrip("/")
    r = _post(base + "/chat/completions",
              {"Authorization": "Bearer " + _setting("CRA_API_KEY"),
               "api-key": _setting("CRA_API_KEY"),        # Azure reads this one
               "Content-Type": "application/json"},
              {"model": model_name("openai"), "temperature": 0,
               "max_tokens": MAX_TOKENS,
               "messages": [{"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}]})
    LAST_USAGE.clear()
    LAST_USAGE.update(r.get("usage", {}))
    return r["choices"][0]["message"]["content"]


def _anthropic(system_prompt, user_prompt):
    base = (_setting("CRA_API_BASE") or "https://api.anthropic.com").rstrip("/")
    r = _post(base + "/v1/messages",
              {"x-api-key": _setting("CRA_API_KEY"),
               "anthropic-version": "2023-06-01",
               "Content-Type": "application/json"},
              {"model": model_name("anthropic"), "max_tokens": MAX_TOKENS,
               "temperature": 0,
               # the instructions never change, so they are cached
               "system": [{"type": "text", "text": system_prompt,
                           "cache_control": {"type": "ephemeral"}}],
               "messages": [{"role": "user", "content": user_prompt}]})
    LAST_USAGE.clear()
    LAST_USAGE.update(r.get("usage", {}))
    return "".join(b.get("text", "") for b in r.get("content", []))


# ---------------------------------------------------------------------------
# paste mode
# ---------------------------------------------------------------------------
INSTRUCTIONS = """
--------------------------------------------------------------------------
PASTE MODE

  1. Open  %s
  2. Copy all of it into the ChatGPT website.
  3. Copy ChatGPT's reply.
  4. Paste the reply into  %s  and save it.
  5. Run the same command again.

What is in that file: the check name, the headline and the counts this app
already worked out. There is no patient record in it. Read it before you
paste it. If you can see something that should not leave the company, stop
and tell someone.
--------------------------------------------------------------------------
""" % (PROMPT_FILE, ANSWER_FILE)


def _paste(system_prompt, user_prompt):
    os.makedirs("out", exist_ok=True)
    text = system_prompt + "\n\n" + user_prompt

    old = ""
    if os.path.exists(PROMPT_FILE):
        with open(PROMPT_FILE, encoding="utf-8") as fh:
            old = fh.read()
    if old != text:
        with open(PROMPT_FILE, "w", encoding="utf-8") as fh:
            fh.write(text)

    fresh = (os.path.exists(ANSWER_FILE)
             and os.path.getmtime(ANSWER_FILE) >= os.path.getmtime(PROMPT_FILE))
    if fresh:
        with open(ANSWER_FILE, encoding="utf-8") as fh:
            answer = fh.read().strip()
        if answer:
            return answer

    if sys.stdin and sys.stdin.isatty():
        print(INSTRUCTIONS)
        input("Press Enter once you have saved the reply, or Ctrl+C to stop: ")
        if os.path.exists(ANSWER_FILE):
            with open(ANSWER_FILE, encoding="utf-8") as fh:
                answer = fh.read().strip()
            if answer:
                return answer

    raise RuntimeError(
        "Paste mode needs an answer. The prompt is in %s. Put ChatGPT's reply "
        "in %s and run this again." % (PROMPT_FILE, ANSWER_FILE))


# ---------------------------------------------------------------------------
# mock mode
# ---------------------------------------------------------------------------
_SEVERITY = {
    "paired_comparison_same_n": "Critical",
    "exclusion_applied_consistently": "Critical",
    "study_and_protocol_consistent": "Critical",
    "outputs_present_vs_shells": "Critical",
    "denominator_vs_population": "Critical",
    "counts_dip_and_return": "Major",
    "title_range_vs_values": "Major",
    "duplicate_titles": "Major",
    "n_consistent_across_outputs": "Major",
    "rule_stated_not_applied": "Major",
    "percent_without_denominator": "Major",
    "source_line_present": "Major",
    "n_drops_without_footnote": "Major",
}

# Candidates the mock keeps, so the app shows something sensible with no key.
_MOCK_KEEPS = {"treatment_columns_present", "footnote_matches_domain",
               "raw_vs_sdtm_count", "raw_text_in_numbers"}


def _mock(user_prompt):
    """
    Pretend AI. Keeps a few candidates, drops the rest, and writes no words:
    the code's own sentences are kept, so the app never looks like it is
    reasoning when it is not.
    """
    if "\nQUESTION\n" in user_prompt:
        from .ask import mock_answer
        context, _, question = user_prompt.partition("\nQUESTION\n")
        return mock_answer(context, question.strip())

    try:
        items = json.loads(user_prompt.split("ITEMS_JSON:")[-1].strip())
    except Exception:
        return "[]"

    out = []
    for item in items:
        check = item.get("chk", item.get("check", ""))
        certain = item.get("conf", item.get("confidence")) == "certain"
        out.append({"i": item.get("i", item.get("index")),
                    "keep": certain or check in _MOCK_KEEPS,
                    "sev": _SEVERITY.get(check, "Minor"), "why": ""})
    return json.dumps(out)
