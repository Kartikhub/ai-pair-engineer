import os

import streamlit as st
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from prompts import MODE_INSTRUCTIONS, REFACTOR_PROMPT, REVIEW_PROMPT


def _get_secret(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]
    except (FileNotFoundError, KeyError):
        return os.environ.get(key, default)


def _content_to_markdown(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if text:
                    parts.append(text)
            else:
                parts.append(str(block))
        return "\n\n".join(parts)

    return str(content)


def run_ai_review(
    code: str,
    file_name: str,
    assistant_mode: str,
    scenario: str,
) -> str:
    load_dotenv()

    api_key = _get_secret("GOOGLE_API_KEY")
    if not api_key:
        return (
            "## Configuration Needed\n\n"
            "Set `GOOGLE_API_KEY` in your environment or `.env` file, then run the "
            "engineering assistance flow again."
        )

    model_name = _get_secret("GEMINI_MODEL", "gemini-1.5-flash")
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=0.2,
    )

    chain = REVIEW_PROMPT | llm
    response = chain.invoke(
        {
            "assistant_mode": assistant_mode,
            "mode_instruction": MODE_INSTRUCTIONS[assistant_mode],
            "scenario": scenario,
            "code": code,
            "file_name": file_name,
        }
    )
    return _content_to_markdown(response.content)


def generate_targeted_refactor(
    code: str,
    file_name: str,
    assistant_mode: str,
    scenario: str,
    guidance: str,
) -> str:
    load_dotenv()

    api_key = _get_secret("GOOGLE_API_KEY")
    if not api_key:
        return (
            "## Configuration Needed\n\n"
            "Set `GOOGLE_API_KEY` in your environment or `.env` file, then generate "
            "the targeted refactor again."
        )

    model_name = _get_secret("GEMINI_MODEL", "gemini-1.5-flash")
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=0.15,
    )

    chain = REFACTOR_PROMPT | llm
    response = chain.invoke(
        {
            "assistant_mode": assistant_mode,
            "scenario": scenario,
            "file_name": file_name,
            "guidance": guidance,
            "code": code,
        }
    )
    return _content_to_markdown(response.content)
