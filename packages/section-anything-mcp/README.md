# section-anything-mcp

<!-- mcp-name: io.github.Omniwot/section-anything -->

The [Section Anything](https://github.com/Omniwot/section-anything) MCP server, packaged so that
MCP clients can start it with `uvx section-anything-mcp`. It installs `section-anything[mcp]` and
runs its server on stdio. Installing `section-anything[mcp]` yourself gives the same
`section-anything-mcp` command.

Tools (read-only): `section_pdf` (a PDF's heading tree: levels, parents, heading paths, pages,
character spans), `read_sections` (the text of chosen sections) and `estimate_cost` (what Quick
check and Standard would cost). Free mode by default: local, no model, $0.

```sh
claude mcp add --transport stdio section-anything -- uvx section-anything-mcp
```

Options: `--root DIR` (only read PDFs under DIR; repeatable) and `--max-usd` (the per-document cap
for paid modes; 0 keeps every run free). Paid modes read `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`
from the server's environment. Section text is the document's content: treat it as data.

Apache-2.0. Documentation: the main repository's README, "Use from an agent".
