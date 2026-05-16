#!/usr/bin/env python3
"""Analyze raw ACP traffic JSONL from agent-shell.

Usage:
  python3 scripts/analyze-transcript.py path/to/claude.jsonl

Produces a summary report of sessions, token usage, tool calls, and costs.
Enrichment is done on-the-fly from the raw JSON-RPC traffic.
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime


def load_events(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def get_object(entry):
    return entry.get("object") or {}


def get_method(obj, entry=None):
    m = obj.get("method")
    if m:
        return m
    # response (has result but no method)
    if obj.get("result") is not None:
        return "response"
    if obj.get("error"):
        return "error"
    return None


def extract_session_id(obj):
    result = obj.get("result") or {}
    sess = result.get("session") or {}
    sid = sess.get("id") or result.get("sessionId")
    return sid


def analyze(events):
    sessions = defaultdict(lambda: {
        "user_messages": [],
        "agent_messages": [],
        "thoughts": [],
        "tool_calls": [],
        "turns": 0,
        "total_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "thought_tokens": 0,
        "total_cost": 0.0,
        "started": None,
        "ended": None,
        "model": None,
        "mode": None,
        "title": None,
        "cwd": None,
        "methods": Counter(),
    })

    tool_type_counter = Counter()
    current_session_id = "unknown"
    pending_new_session = None

    for ev in events:
        direction = ev.get("direction", "")
        kind = ev.get("kind", "")
        obj = get_object(ev)
        method = get_method(obj)
        ts = ev.get("timestamp")
        params = obj.get("params") or {}
        update = params.get("update") or {}
        session_update = update.get("sessionUpdate") or ""

        # Track session creation from outgoing requests
        if direction == "outgoing" and kind == "request" and method == "session/new":
            params_body = obj.get("params") or {}
            pending_new_session = {
                "cwd": params_body.get("cwd"),
                "ts": ts,
            }
            current_session_id = "pending"

        # Track session response (get id + model)
        elif direction == "incoming" and kind == "response" and method == "response":
            sid = extract_session_id(obj)
            if sid:
                current_session_id = sid
                sess = sessions[sid]
                result = obj.get("result") or {}
                sess_obj = result.get("session") or {}
                if sess_obj.get("model") or sess_obj.get("model-id"):
                    sess["model"] = sess_obj.get("model") or sess_obj.get("model-id")
                sess_mode = result.get("mode") or {}
                if sess_mode.get("mode") or sess_mode.get("mode-id"):
                    sess["mode"] = sess_mode.get("mode") or sess_mode.get("mode-id")
                if ts:
                    t = _parse_time(ts)
                    if sess["started"] is None or t < sess["started"]:
                        sess["started"] = t
                    if sess["ended"] is None or t > sess["ended"]:
                        sess["ended"] = t
                # Transfer pending metadata
                if pending_new_session:
                    if pending_new_session["ts"]:
                        req_ts = _parse_time(pending_new_session["ts"])
                        if sess["started"] is None or (req_ts and req_ts < sess["started"]):
                            sess["started"] = req_ts
                    sess["cwd"] = pending_new_session["cwd"]
                    pending_new_session = None

        sess = sessions.get(current_session_id) or sessions["unknown"]

        if ts:
            t = _parse_time(ts)
            if sess["started"] is None or t < sess["started"]:
                sess["started"] = t
            if sess["ended"] is None or t > sess["ended"]:
                sess["ended"] = t

        if direction == "incoming" and kind == "notification":
            if session_update == "agent_thought_chunk":
                text = _get_text(update)
                if text:
                    sess["thoughts"].append(text)
            elif session_update == "agent_message_chunk":
                text = _get_text(update)
                if text:
                    sess["agent_messages"].append(text)
            elif session_update == "user_message_chunk":
                text = _get_text(update)
                if text:
                    sess["user_messages"].append(text)
            elif session_update == "tool_call":
                sess["turns"] += 1
                tool_info = {
                    "title": update.get("title", ""),
                    "kind": update.get("kind", ""),
                    "status": update.get("status", ""),
                }
                tool_type_counter[tool_info["kind"] or tool_info["title"] or "unknown"] += 1
                sess["tool_calls"].append(tool_info)
                # Check for usage data (turn-complete signal)
                usage = update.get("usage") or obj.get("result", {}).get("usage", {})
                _accumulate_usage(sess, usage)

            elif session_update == "tool_call_update":
                # Tool call updates include status changes
                usage = update.get("usage") or {}
                _accumulate_usage(sess, usage)

            elif session_update == "plan":
                pass  # Plan entries don't need special handling

        # Also check for usage in response messages
        if direction == "incoming" and kind == "response":
            result = obj.get("result") or {}
            usage = result.get("usage") or {}
            if usage:
                _accumulate_usage(sess, usage)

    return sessions, tool_type_counter


def _parse_time(ts):
    """Parse ISO timestamp to datetime."""
    try:
        return datetime.strptime(ts.rsplit("+", 1)[0], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, IndexError):
        return None


def _get_text(update):
    """Extract text content from an ACP update."""
    content = update.get("content") or {}
    if isinstance(content, list):
        texts = [c.get("text", "") for c in content if isinstance(c, dict)]
        return " ".join(t.strip() for t in texts if t.strip())
    return content.get("text", "") or ""


def _accumulate_usage(sess, usage):
    """Accumulate token/cost metrics from usage data."""
    tokens_total = usage.get("totalTokens", 0) or usage.get("total-tokens", 0) or 0
    sess["total_tokens"] += tokens_total
    sess["input_tokens"] += usage.get("inputTokens", 0) or usage.get("input-tokens", 0) or 0
    sess["output_tokens"] += usage.get("outputTokens", 0) or usage.get("output-tokens", 0) or 0
    sess["thought_tokens"] += usage.get("thoughtTokens", 0) or usage.get("thought-tokens", 0) or 0
    cost = usage.get("costAmount", 0) or usage.get("cost-amount", 0) or 0.0
    sess["total_cost"] += cost


def print_report(sessions, tool_type_counter):
    print("=" * 60)
    print("AGENT-SHELL ACP TRAFFIC ANALYSIS")
    print("=" * 60)
    print(f"\nSessions: {len(sessions)}")

    for sid, s in sorted(sessions.items()):
        if sid == "unknown" and not s["user_messages"] and not s["agent_messages"] and s["total_tokens"] == 0:
            continue
        print(f"\n{'─' * 50}")
        print(f"Session: {sid}")
        if s.get("model"):
            print(f"  Model:       {s['model']}")
        if s.get("mode"):
            print(f"  Mode:        {s['mode']}")
        if s["started"]:
            print(f"  Started:     {s['started']}")
        if s["ended"]:
            print(f"  Ended:       {s['ended']}")
            if s["started"]:
                print(f"  Duration:    {s['ended'] - s['started']}")
        if s["total_tokens"] > 0:
            print(f"  Total tokens: {s['total_tokens']:,}")
            print(f"  Input tokens:  {s['input_tokens']:,}")
            print(f"  Output tokens: {s['output_tokens']:,}")
            if s["thought_tokens"] > 0:
                print(f"  Thought tokens:{s['thought_tokens']:,}")
        if s["total_cost"] > 0:
            print(f"  Total cost:   ${s['total_cost']:.4f}")
        print(f"  Turns:         {s['turns']}")
        print(f"  User messages: {len(s['user_messages'])}")
        print(f"  Agent messages:{len(s['agent_messages'])}")
        print(f"  Thoughts:      {len(s['thoughts'])}")
        print(f"  Tool calls:    {len(s['tool_calls'])}")
        if s["user_messages"]:
            topics = [m[:80] for m in s["user_messages"] if m]
            print(f"  Topics:")
            for t in topics[:5]:
                print(f"    - {t}")

    if tool_type_counter:
        print(f"\n{'─' * 50}")
        print("TOOL USAGE")
        for tool, count in tool_type_counter.most_common(15):
            print(f"  {tool:>20}: {count}")

    print("=" * 60)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <traffic.jsonl>", file=sys.stderr)
        sys.exit(1)

    events = load_events(sys.argv[1])
    print(f"Loaded {len(events)} raw ACP events from {sys.argv[1]}")
    sessions, tool_type_counter = analyze(events)
    print_report(sessions, tool_type_counter)


if __name__ == "__main__":
    main()
