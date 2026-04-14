"""
graph-autotagger-mcp: FastMCP server that reads a pre-computed knowledge graph
and suggests wikilinks, God Node connections, and community memberships for
Obsidian vault notes.

Configuration via environment variables:
    GRAPH_JSON_PATH  — path to graph.json (default: ~/vault/.graph/graph.json)
    AUTOTAGGER_DB    — path to SQLite suggestion log (default: ~/.config/graph-autotagger/log.db)
"""

import json
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAPH_PATH = Path(
    os.environ.get("GRAPH_JSON_PATH", str(Path.home() / "vault" / ".graph" / "graph.json"))
)
DB_PATH = Path(
    os.environ.get("AUTOTAGGER_DB", str(Path.home() / ".config" / "graph-autotagger" / "log.db"))
)

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "through", "is",
    "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "shall", "can", "it", "its", "this", "that", "these", "those", "i",
    "me", "my", "we", "our", "you", "your", "he", "she", "they", "them",
    "his", "her", "their", "what", "which", "who", "when", "where", "how",
    "all", "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "no", "not", "only", "same", "so", "than", "too", "very",
    "just", "as", "if", "then", "there", "here", "also", "any", "now",
}

# ---------------------------------------------------------------------------
# Graph loading (lazy, cached)
# ---------------------------------------------------------------------------

_graph_data: Optional[dict] = None
_node_index: Optional[dict] = None       # id -> node dict
_degree_index: Optional[dict] = None     # id -> degree count
_community_index: Optional[dict] = None  # community_id -> list[node]


def _load_graph() -> tuple[dict, dict, dict, dict]:
    """Load graph once and cache. Returns (graph_data, node_index, degree_index, community_index)."""
    global _graph_data, _node_index, _degree_index, _community_index

    if _graph_data is not None:
        return _graph_data, _node_index, _degree_index, _community_index

    if not GRAPH_PATH.exists():
        raise FileNotFoundError(
            f"graph.json not found at {GRAPH_PATH}. "
            f"Set GRAPH_JSON_PATH env var or run graphify first."
        )

    with open(GRAPH_PATH, encoding="utf-8") as f:
        _graph_data = json.load(f)

    # Build node index
    _node_index = {n["id"]: n for n in _graph_data.get("nodes", []) if "id" in n}

    # Build degree index from links (networkx to_json() uses "links", not "edges")
    _degree_index = defaultdict(int)
    for link in _graph_data.get("links", []):
        src = link.get("source")
        tgt = link.get("target")
        if src:
            _degree_index[src] += 1
        if tgt:
            _degree_index[tgt] += 1

    # Build community index (nodes use "community" field)
    _community_index = defaultdict(list)
    for node in _graph_data.get("nodes", []):
        cid = node.get("community")
        if cid is not None:
            _community_index[cid].append(node)

    return _graph_data, _node_index, _degree_index, _community_index


# ---------------------------------------------------------------------------
# SQLite setup
# ---------------------------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    """Return a SQLite connection, creating the table if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suggestion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_title TEXT NOT NULL,
            node_label TEXT NOT NULL,
            decision TEXT NOT NULL,
            logged_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Tokenize text into meaningful lowercase terms, removing stopwords."""
    tokens = re.split(r"[\s\W_]+", text.lower())
    return {t for t in tokens if t and len(t) > 2 and t not in STOPWORDS}


def _extract_wikilinks(text: str) -> set[str]:
    """Extract all [[label]] wikilinks from text, lowercased."""
    return {m.lower() for m in re.findall(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]", text)}


def _label_tokens(label: str) -> set[str]:
    """Tokenize a node label."""
    return _tokenize(label)


def _overlap_score(note_tokens: set[str], label_tokens: set[str]) -> float:
    """
    Compute overlap score: intersection / len(label_tokens).
    Falls back to substring match bonus.
    """
    if not label_tokens:
        return 0.0
    overlap = note_tokens & label_tokens
    return len(overlap) / len(label_tokens)


def _is_private_node(node: dict) -> bool:
    """Heuristic: node is explicitly private/personal-only."""
    label = (node.get("label") or "").lower()
    src = (node.get("source_file") or "").lower()
    return "private" in label or "personal-only" in label or "private" in src


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("graph-autotagger")


@mcp.tool()
def suggest_links(
    note_content: str,
    note_title: str = "",
    max_suggestions: int = 8,
) -> list[dict]:
    """
    Suggest wikilinks for an Obsidian note based on the knowledge graph.

    Returns a list of {node_id, label, confidence, reason} sorted by confidence desc.
    """
    try:
        _, node_index, _, _ = _load_graph()
    except FileNotFoundError as e:
        return [{"error": str(e)}]

    note_tokens = _tokenize(note_content + " " + note_title)
    existing_links = _extract_wikilinks(note_content)

    results = []
    for node in node_index.values():
        label = node.get("label", "")
        if not label:
            continue

        # Skip if already wikilinked
        if label.lower() in existing_links:
            continue

        # Skip private nodes
        if _is_private_node(node):
            continue

        label_toks = _label_tokens(label)
        score = _overlap_score(note_tokens, label_toks)

        # Bonus: full label appears as substring in note content
        if label.lower() in note_content.lower() and score == 0.0:
            score = 0.3
        elif label.lower() in note_content.lower():
            score = min(1.0, score + 0.2)

        if score <= 0.0:
            continue

        confidence = round(min(1.0, score), 4)
        overlap = note_tokens & label_toks
        reason = f"Matched terms: {', '.join(sorted(overlap))}" if overlap else f"Label '{label}' found in note text"

        results.append({
            "node_id": node["id"],
            "label": label,
            "confidence": confidence,
            "reason": reason,
        })

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results[:max_suggestions]


@mcp.tool()
def check_god_nodes(note_content: str) -> list[dict]:
    """
    Check which God Nodes (top 20 by degree) are relevant to the note.

    God Nodes are the most connected concepts in your vault. Linking to them
    creates high-value connections to the core ideas in your knowledge graph.

    Returns {node_id, label, degree, linked, should_link, reason} for each God Node.
    """
    try:
        _, node_index, degree_index, _ = _load_graph()
    except FileNotFoundError as e:
        return [{"error": str(e)}]

    existing_links = _extract_wikilinks(note_content)
    note_lower = note_content.lower()

    # Get top 20 nodes by degree
    top_ids = sorted(degree_index.keys(), key=lambda nid: degree_index[nid], reverse=True)[:20]

    results = []
    for nid in top_ids:
        node = node_index.get(nid)
        if not node:
            continue

        label = node.get("label", "")
        degree = degree_index[nid]
        linked = label.lower() in existing_links
        relevant = label.lower() in note_lower

        should_link = relevant and not linked
        reason = ""
        if linked:
            reason = "Already wikilinked in note."
        elif relevant:
            reason = f"Label '{label}' found in note text; consider linking."
        else:
            reason = "Not mentioned in note."

        results.append({
            "node_id": nid,
            "label": label,
            "degree": degree,
            "linked": linked,
            "should_link": should_link,
            "reason": reason,
        })

    return results


@mcp.tool()
def community_match(note_content: str, max_matches: int = 3) -> list[dict]:
    """
    Find which graph communities the note most closely belongs to.

    Returns top max_matches communities: {community_id, match_score, matching_nodes, total_nodes_in_community}.
    """
    try:
        _, _, _, community_index = _load_graph()
    except FileNotFoundError as e:
        return [{"error": str(e)}]

    note_lower = note_content.lower()
    note_tokens = _tokenize(note_content)

    scored = []
    for cid, nodes in community_index.items():
        matched_labels = []
        for node in nodes:
            label = node.get("label", "")
            if not label:
                continue
            label_toks = _label_tokens(label)
            overlap = note_tokens & label_toks
            if label.lower() in note_lower or (len(overlap) >= 2):
                matched_labels.append(label)

        if matched_labels:
            match_score = round(len(matched_labels) / max(len(nodes), 1), 4)
            scored.append({
                "community_id": cid,
                "match_score": match_score,
                "matching_nodes": matched_labels[:20],
                "total_nodes_in_community": len(nodes),
            })

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored[:max_matches]


@mcp.tool()
def log_suggestion_decision(
    note_title: str,
    node_label: str,
    decision: str,
) -> dict:
    """
    Log whether a suggested wikilink was accepted, rejected, or ignored.

    decision must be one of: 'accepted', 'rejected', 'ignored'.
    """
    valid_decisions = {"accepted", "rejected", "ignored"}
    if decision not in valid_decisions:
        return {
            "success": False,
            "error": f"Invalid decision '{decision}'. Must be one of: {', '.join(sorted(valid_decisions))}",
        }

    logged_at = datetime.now(timezone.utc).isoformat()
    try:
        conn = _get_db()
        conn.execute(
            "INSERT INTO suggestion_log (note_title, node_label, decision, logged_at) VALUES (?, ?, ?, ?)",
            (note_title, node_label, decision, logged_at),
        )
        conn.commit()
        conn.close()
        return {"success": True, "logged_at": logged_at}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Self-test (run with: python3 server.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) == 1:
        # Self-test mode
        TEST_TEXT = (
            "Building a marketplace for events. "
            "Budget management and revenue strategy are key themes."
        )

        print("=" * 60)
        print("SELF-TEST: graph-autotagger-mcp")
        print("=" * 60)
        print(f"Graph path: {GRAPH_PATH}")
        print(f"DB path:    {DB_PATH}")

        print("\n[1] suggest_links")
        print(f"    Input: {TEST_TEXT!r}")
        try:
            results = suggest_links(TEST_TEXT, note_title="Test Note")
            for r in results:
                print(f"    - [{r.get('confidence', 0):.2f}] {r.get('label', r)!r}: {r.get('reason', '')}")
            print(f"    => {len(results)} suggestions returned")
        except Exception as e:
            print(f"    ERROR: {e}")
            sys.exit(1)

        print("\n[2] check_god_nodes")
        try:
            results = check_god_nodes(TEST_TEXT)
            for r in results:
                flag = "SHOULD LINK" if r.get("should_link") else ("linked" if r.get("linked") else "not mentioned")
                print(f"    - deg={r.get('degree', 0):4d} {r.get('label', '')!r}: {flag}")
            print(f"    => {len(results)} god nodes checked")
        except Exception as e:
            print(f"    ERROR: {e}")
            sys.exit(1)

        print("\n[3] community_match")
        try:
            results = community_match(TEST_TEXT)
            for r in results:
                print(
                    f"    - community={r['community_id']} score={r['match_score']:.4f} "
                    f"({len(r['matching_nodes'])}/{r['total_nodes_in_community']} nodes matched)"
                )
            print(f"    => {len(results)} community matches returned")
        except Exception as e:
            print(f"    ERROR: {e}")
            sys.exit(1)

        print("\nSelf-test complete.")
        sys.exit(0)
    else:
        mcp.run()
