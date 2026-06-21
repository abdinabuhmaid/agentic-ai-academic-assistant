"""
base_agent.py
-------------
Shared logic that every agent uses to call the Groq API. Centralising this
means the three agents stay short and consistent, and any change to how we
call the model happens in one place.
"""

import json

from config import client, MODEL


def call_llm(system_prompt, user_prompt, model=MODEL, temperature=0.3, json_mode=False):
    """
    Send one request to the Groq chat API and return the model's text reply.

    Set json_mode=True to force the model to return a valid JSON object
    (used by the Research and Grading agents). When json_mode is on, the
    prompt itself must also ask for JSON — which our templates do.
    """
    kwargs = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content


def call_llm_json(system_prompt, user_prompt, model=MODEL, temperature=0.2):
    """
    Same as call_llm but parses the reply into a Python dict.
    Raises a clear error if the model returns something that isn't valid JSON.
    """
    raw = call_llm(system_prompt, user_prompt, model=model,
                   temperature=temperature, json_mode=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Model did not return valid JSON:\n{raw}") from e
