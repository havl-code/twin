import json
import os
import requests
from dotenv import load_dotenv

from context import OWNER_EMAILS

load_dotenv(override=True)

pushover_user = os.getenv("PUSHOVER_USER")
pushover_token = os.getenv("PUSHOVER_TOKEN")

pushover_url = "https://api.pushover.net/1/messages.json"


def push(text):
    requests.post(
        pushover_url,
        data={
            "token": pushover_token,
            "user": pushover_user,
            "message": text,
        },
    )


def record_user_details(email=None, name="Name not provided", notes="not provided"):
    if email:
        if email.strip().lower() in OWNER_EMAILS:
            return "That's my own email address, not yours. Please ask the visitor for their own email address instead."
        push(f"Recording interest from {name} with email {email} and notes {notes}")
    else:
        push("A visitor is interested in getting in touch, but didn't share an email address.")
    return "OK"


def record_unknown_question(question):
    push(f"Recording {question} asked that I couldn't answer")
    return "OK"


record_user_details_json = {
    "name": "record_user_details",
    "description": (
        "Use this tool to record that a visitor is interested in getting in touch. Call it once the "
        "visitor has confirmed they want to be contacted, whether or not they chose to share an email "
        "address. Never call this with the represented person's own email address or any email pulled "
        "from background context, only an email the visitor themselves typed in the chat."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "description": (
                    "The visitor's own email address, exactly as they typed it in the chat just now. "
                    "Omit this if the visitor didn't want to share one, it's optional."
                ),
            },
            "name": {"type": "string", "description": "The user's name, if they provided it"},
            "notes": {
                "type": "string",
                "description": "Any additional info about the conversation that's worth recording to give context",
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}

record_unknown_question_json = {
    "name": "record_unknown_question",
    "description": (
        "Use this ONLY when you genuinely do not know the answer and are about to tell the visitor "
        "that in your reply. If you can answer the question at all from the background info you have "
        "(summary, LinkedIn, fun facts, etc.), even partially, do NOT call this tool, just answer "
        "normally. For example, questions about the fun facts section (e.g. why there's a lightning "
        "bolt icon on the site) ARE answerable, so never call this tool for those."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "The question that couldn't be answered"},
        },
        "required": ["question"],
        "additionalProperties": False,
    },
}

tools = [
    {"type": "function", "function": record_user_details_json},
    {"type": "function", "function": record_unknown_question_json},
]

tool_map = {
    "record_user_details": record_user_details,
    "record_unknown_question": record_unknown_question,
}


def handle_tool_calls(tool_calls):
    results = []
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        print(f"Tool called: {tool_name}", flush=True)
        tool = tool_map.get(tool_name)
        result = tool(**arguments) if tool else "Unknown tool: " + tool_name
        results.append(
            {"role": "tool", "content": json.dumps(result), "tool_call_id": tool_call.id}
        )
    return results
