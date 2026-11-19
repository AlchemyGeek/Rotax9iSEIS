"""
Investigations (Spec 16): what the user's own Claude reaches through the
MCP server — the aircraft document, the workspace's documents, notebook
studies, the code bench and the Research inbox. Every piece here is a
host operation first (Spec 01 §7 envelope); the MCP server
(`mcp_server.py`) is a façade over those operations.

Nothing in this package runs an AI, calls out, or stores anything on
anyone's behalf (Spec 16 §2.7).
"""
