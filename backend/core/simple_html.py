"""
Tiny standalone HTML pages for links clicked directly from email/dashboard
(full-page navigations, not XHR from the frontend build) — unsubscribe
confirmations, broken apply-link errors, etc. No build step, no JS,
inlined design-system tokens (docs/design-system.md) so it never depends
on the frontend deploy being healthy.
"""
from __future__ import annotations

_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; background: #F8FAFC; color: #0F2F3A;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 24px; }}
  .card {{ max-width: 420px; width: 100%; background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px;
           padding: 32px; text-align: center; }}
  h1 {{ font-size: 20px; margin: 0 0 12px; }}
  p {{ font-size: 14px; color: #64748B; line-height: 1.6; margin: 0; }}
  a {{ color: #B45309; }}
</style></head>
<body><div class="card"><h1>{heading}</h1><p>{body}</p></div></body></html>"""


def render_message_page(title: str, heading: str, body: str) -> str:
    return _PAGE.format(title=title, heading=heading, body=body)
