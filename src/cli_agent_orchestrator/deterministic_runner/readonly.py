"""Read-only MCP/tool policy guards for deterministic mode."""

READ_ONLY_ALLOWED_TOOLS = {"fs_read", "fs_list", "@repo-read"}
READ_ONLY_REQUIRED_MCP_SERVER = "repo-read"


def assert_readonly_policy(
    agent_name: str,
    allowed_tools: list[str],
    mcp_servers: list[str],
) -> None:
    if not allowed_tools:
        raise ValueError(
            f"{agent_name}: allowed_tools must be explicitly set for deterministic mode"
        )
    disallowed = sorted(tool for tool in allowed_tools if tool not in READ_ONLY_ALLOWED_TOOLS)
    if disallowed:
        raise ValueError(
            f"{agent_name}: disallowed tools for read-only mode: {','.join(disallowed)}"
        )
    normalized_servers = sorted({name.strip() for name in mcp_servers if name.strip()})
    if normalized_servers != [READ_ONLY_REQUIRED_MCP_SERVER]:
        raise ValueError(
            f"{agent_name}: mcp_servers must be exactly [{READ_ONLY_REQUIRED_MCP_SERVER}]"
        )
