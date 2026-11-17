"""
Compatibility shim for `prospects.email_summarizer`.
All Email AI & Manager Email Activity summarization code now resides in the
`email_ai` Django app (`email_ai.services`).
"""

from email_ai.services import (  # noqa: F401
    _build_daily_user_llm_prompt,
    _build_llm_prompt,
    _call_gemini,
    _call_openai,
    _clean_message_text,
    _discover_gemini_models,
    _generate_daily_user_extractive_summary,
    _generate_extractive_summary,
    _get_setting,
    _parse_json_summary,
    _resolve_provider_and_key,
    _strip_html,
    _truncate_words,
    compute_thread_content_hash,
    generate_daily_user_email_report,
    schedule_thread_summary,
    summarize_email_thread,
)
