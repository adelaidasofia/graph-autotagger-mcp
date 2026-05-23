# graph-autotagger-mcp


<!-- mycelium-badges:start -->

<p>
  <a href="https://github.com/adelaidasofia/graph-autotagger-mcp/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/adelaidasofia/graph-autotagger-mcp?color=blue"></a>
  <a href="https://github.com/adelaidasofia/graph-autotagger-mcp/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/adelaidasofia/graph-autotagger-mcp?color=eab308"></a>
  <a href="https://github.com/adelaidasofia/graph-autotagger-mcp/commits/main"><img alt="Last commit" src="https://img.shields.io/github/last-commit/adelaidasofia/graph-autotagger-mcp"></a>
  <a href="https://github.com/adelaidasofia/graph-autotagger-mcp/issues"><img alt="Open issues" src="https://img.shields.io/github/issues/adelaidasofia/graph-autotagger-mcp"></a>
  <a href="https://pypi.org/project/adelaidasofia-graph-autotagger-mcp/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/adelaidasofia-graph-autotagger-mcp?color=blue&label=pypi"></a>
  <a href="https://pypi.org/project/adelaidasofia-graph-autotagger-mcp/"><img alt="PyPI downloads" src="https://img.shields.io/pypi/dm/adelaidasofia-graph-autotagger-mcp?color=blue&label=downloads"></a>
  <a href="https://myceliumai.co"><img alt="Built by Mycelium AI" src="https://img.shields.io/badge/built_by-Mycelium_AI-15B89A"></a>
</p>

<!-- mycelium-badges:end -->

A FastMCP server that reads a pre-computed Obsidian knowledge graph and suggests wikilinks for your notes. Designed as a companion to [graphify](https://github.com/adelaidasofia/graphify) — run graphify to build the graph, then this MCP surfaces connections as you write.

## Tools

| Tool | What it does |
|------|-------------|
| `suggest_links` | Suggest wikilinks for a note based on token overlap with graph node labels |
| `check_god_nodes` | Check which highly-connected nodes (top 20 by degree) are relevant to the note |
| `community_match` | Find which graph communities the note most closely belongs to |
| `log_suggestion_decision` | Log accepted/rejected/ignored decisions to a local SQLite database |

## Install

Open Claude Code, paste:

    /plugin marketplace add adelaidasofia/graph-autotagger-mcp
    /plugin install graph-autotagger-mcp@graph-autotagger-mcp

After install, set `GRAPH_JSON_PATH` (see Environment variables below) and restart Claude Code, then ask:
> "Suggest wikilinks for this note: [paste note content]"

<details>
<summary>Legacy install</summary>

```bash
pip install fastmcp
```

1. Clone:
   ```bash
   git clone https://github.com/adelaidasofia/graph-autotagger-mcp.git
   cd graph-autotagger-mcp
   ```

2. Set the path to your graph.json:
   ```bash
   export GRAPH_JSON_PATH="~/vault/.graph/graph.json"
   ```
   Or pass it at registration time (see below).

3. Self-test:
   ```bash
   python3 server.py
   ```

4. Register with Claude Code:
   ```bash
   claude mcp add graph-autotagger -s user -- \
     env GRAPH_JSON_PATH="$HOME/vault/.graph/graph.json" \
     python3 /path/to/graph-autotagger-mcp/server.py
   ```

5. Restart Claude Code, then ask:
   > "Suggest wikilinks for this note: [paste note content]"

</details>

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAPH_JSON_PATH` | `~/vault/.graph/graph.json` | Path to your graphify output |
| `AUTOTAGGER_DB` | `~/.config/graph-autotagger/log.db` | SQLite log for suggestion decisions |

## How it works

The server loads `graph.json` once at startup and caches it in memory. Node labels are tokenized and matched against note content using token overlap scoring. God Nodes (top 20 by degree) get special treatment since connecting to them creates high-value cross-links.

The `log_suggestion_decision` tool lets you build a feedback dataset over time: accepted suggestions can be used to tune the relevance threshold; rejected ones reveal graph noise.

## graph.json format

Expects the output format from graphify (networkx `node_link_data`):

```json
{
  "nodes": [{"id": "node-id", "label": "Node Label", "community": 0}],
  "links": [{"source": "node-a", "target": "node-b"}]
}
```

Note: networkx serializes edges under `"links"`, not `"edges"`.

## Related MCPs

Same author, same architecture pattern (FastMCP, draft+confirm on writes where applicable, vault auto-export, MIT):

- [slack-mcp](https://github.com/adelaidasofia/slack-mcp) - multi-workspace Slack
- [imessage-mcp](https://github.com/adelaidasofia/imessage-mcp) - macOS iMessage
- [whatsapp-mcp](https://github.com/adelaidasofia/whatsapp-mcp) - WhatsApp via whatsmeow
- [google-workspace-mcp](https://github.com/adelaidasofia/google-workspace-mcp) - Gmail / Calendar / Drive / Docs / Sheets
- [apollo-mcp](https://github.com/adelaidasofia/apollo-mcp) - Apollo.io CRM + sequences
- [substack-mcp](https://github.com/adelaidasofia/substack-mcp) - Substack writing + analytics
- [luma-mcp](https://github.com/adelaidasofia/luma-mcp) - lu.ma events
- [parse-mcp](https://github.com/adelaidasofia/parse-mcp) - markitdown / Docling / LlamaParse router
- [rescuetime-mcp](https://github.com/adelaidasofia/rescuetime-mcp) - RescueTime productivity data
- [graph-query-mcp](https://github.com/adelaidasofia/graph-query-mcp) - vault knowledge graph queries
- [investor-relations-mcp](https://github.com/adelaidasofia/investor-relations-mcp) - seed-raise pipeline tracker
- [vault-sync-mcp](https://github.com/adelaidasofia/vault-sync-mcp) - bidirectional vault sync


## Telemetry

This plugin sends a single anonymous install signal to `myceliumai.co` the first time it loads in a Claude Code session on a given machine.

**What is sent:**
- Plugin name (e.g. `slack-mcp`)
- Plugin version (e.g. `0.1.0`)

**What is NOT sent:**
- No user identifiers, names, emails, tokens, or API keys
- No file paths, message content, or anything from your work
- No IP address is stored after dedup processing

**Why:** Helps the maintainer know which plugins people actually install, so attention goes to the ones that get used.

**Opt out:** Set the environment variable `MYCELIUM_NO_PING=1` before launching Claude Code. The hook will skip the network call entirely. Already-pinged installs leave a sentinel at `~/.mycelium/onboarded-<plugin>` — delete it if you want to reset state.

## License

MIT

---

Built by Adelaida Diaz-Roa. Full install or team version at [diazroa.com](https://diazroa.com).
