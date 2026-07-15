# Yandex Tracker MCP Server

![PyPI - Version](https://img.shields.io/pypi/v/yandex-tracker-mcp)
![Test Workflow](https://github.com/sergeyyarin/yandex-tracker-mcp/actions/workflows/test.yml/badge.svg?branch=main)

mcp-name: io.github.sergeyyarin/yandex-tracker-mcp

A task-management-oriented fork of the comprehensive Model Context Protocol (MCP) server for Yandex Tracker. It adds an idempotent development-task workflow, controlled writes, write auditing and current Live Boards creation while retaining the upstream low-level tools.

See the [controlled task-management guide](docs/TASK_MANAGEMENT.md). The upstream PyPI package remains useful for generic installations; build this fork from source or publish its container under `ghcr.io/sergeyyarin/yandex-tracker-mcp` for managed deployments.

<a href="https://glama.ai/mcp/servers/@aikts/yandex-tracker-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@aikts/yandex-tracker-mcp/badge" />
</a>

Documentation in Russian is available [here](README_ru.md) / Документация на русском языке доступна [здесь](README_ru.md).

## Features

- **Complete Queue Management**: List and access all available Yandex Tracker queues with pagination support, tag retrieval, and detailed metadata
- **User Management**: Retrieve user account information, including login details, email addresses, license status, and organizational data
- **Full Issue Lifecycle**: Create, read, update, and manage issues with support for custom fields, attachments, and workflow transitions
- **Status Workflow Management**: Execute status transitions, close issues with resolutions, and navigate complex workflows
- **Field Management**: Access global fields, queue-specific local fields, statuses, issue types, priorities, and resolutions
- **Advanced Query Language**: Full Yandex Tracker Query Language support with complex filtering, sorting, and date functions
- **Performance Caching**: Optional Redis caching layer for improved response times
- **Security Controls**: Configurable queue access restrictions and secure token handling
- **Multiple Transport Options**: Support for stdio, SSE (deprecated), and HTTP transports for flexible integration
- **OAuth 2.0 Authentication**: Dynamic token-based authentication with automatic refresh support as an alternative to static API tokens
- **Organization Support**: Compatible with both standard and cloud organization IDs

### Organization ID Configuration

Choose one of the following based on your Yandex organization type:

- **Yandex Cloud Organization**: Use `TRACKER_CLOUD_ORG_ID` env var later for Yandex Cloud-managed organizations
- **Yandex 360 Organization**: Use `TRACKER_ORG_ID` env var later for Yandex 360 organizations

You can find your organization ID in the Yandex Tracker URL or organization settings.


## MCP Client Configuration

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) installed globally
- Valid Yandex Tracker API token with appropriate permissions

The ChatGPT and Codex examples run this fork from a local checkout. The generic
client examples further below use the upstream PyPI package or container and
may not include this fork's controlled task-management features. A local
container for this fork can be built with
`docker build -t yandex-tracker-mcp:local .`.

Configure one authentication method and one organization identifier:

- Authentication (one of the following):
  - `TRACKER_TOKEN` - Your Yandex Tracker OAuth token
  - `TRACKER_IAM_TOKEN` - Your IAM token
  - `TRACKER_SA_KEY_ID`, `TRACKER_SA_SERVICE_ACCOUNT_ID`, `TRACKER_SA_PRIVATE_KEY` - Service account credentials
- `TRACKER_CLOUD_ORG_ID` or `TRACKER_ORG_ID` - Your Yandex Cloud (or Yandex 360) organization ID

<details>
<summary><strong>ChatGPT desktop app (ChatGPT Work or Codex)</strong></summary>

1. Open **Settings** and select **MCP servers**.
2. Select **Add server** and choose **STDIO**.
3. Set the command to `uv` and the arguments to
   `--directory /absolute/path/to/yandex-tracker-mcp run yandex-tracker-mcp`.
4. Add the required Tracker environment variables, save, and select
   **Restart**.

The ChatGPT desktop app, Codex CLI, and Codex IDE extension share the MCP
configuration for the same Codex host. Use `/mcp` in the composer to inspect
connected servers.

</details>

<details>
<summary><strong>Codex CLI and IDE extension</strong></summary>

**Using a local checkout:**

```bash
codex mcp add yandex-tracker \
  --env TRACKER_TOKEN=your_tracker_token_here \
  --env TRACKER_CLOUD_ORG_ID=your_cloud_org_id_here \
  -- \
  uv --directory /absolute/path/to/yandex-tracker-mcp run yandex-tracker-mcp
```

Use `TRACKER_ORG_ID` instead of `TRACKER_CLOUD_ORG_ID` for Yandex 360.

**Using a locally built Docker image:**

```bash
codex mcp add yandex-tracker \
  --env TRACKER_TOKEN=your_tracker_token_here \
  --env TRACKER_CLOUD_ORG_ID=your_cloud_org_id_here \
  -- \
  docker run --rm -i \
    -e TRACKER_TOKEN \
    -e TRACKER_CLOUD_ORG_ID \
    yandex-tracker-mcp:local
```

For finer control, use `~/.codex/config.toml`, or `.codex/config.toml` in a
trusted project. `env_vars` forwards values from the local environment without
placing secrets in the repository:

```toml
[mcp_servers.yandex-tracker]
command = "uv"
args = ["--directory", "/absolute/path/to/yandex-tracker-mcp", "run", "yandex-tracker-mcp"]
env_vars = ["TRACKER_TOKEN", "TRACKER_IAM_TOKEN", "TRACKER_CLOUD_ORG_ID", "TRACKER_ORG_ID"]
default_tools_approval_mode = "writes"
```

In the IDE extension, open the gear menu, select **MCP servers**, add the same
STDIO command, and restart the extension. Run `codex mcp list` or use `/mcp` in
the Codex TUI to verify the connection.

</details>

<details>
<summary><strong>Cursor</strong></summary>

**Configuration file path:**
- Project-specific: `.cursor/mcp.json` in your project directory
- Global: `~/.cursor/mcp.json`

**Using uvx:**
```json
{
  "mcpServers": {
    "yandex-tracker": {
      "command": "uvx",
      "args": ["yandex-tracker-mcp@latest"],
      "env": {
        "TRACKER_TOKEN": "your_tracker_token_here",
        "TRACKER_CLOUD_ORG_ID": "your_cloud_org_id_here",
        "TRACKER_ORG_ID": "your_org_id_here"
      }
    }
  }
}
```

**Using Docker:**
```json
{
  "mcpServers": {
    "yandex-tracker": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "TRACKER_TOKEN",
        "-e", "TRACKER_CLOUD_ORG_ID",
        "-e", "TRACKER_ORG_ID",
        "ghcr.io/aikts/yandex-tracker-mcp:latest"
      ],
      "env": {
        "TRACKER_TOKEN": "your_tracker_token_here",
        "TRACKER_CLOUD_ORG_ID": "your_cloud_org_id_here",
        "TRACKER_ORG_ID": "your_org_id_here"
      }
    }
  }
}
```

</details>

<details>
<summary><strong>Windsurf</strong></summary>

**Configuration file path:**
- `~/.codeium/windsurf/mcp_config.json`

Access via: Windsurf Settings → Cascade tab → Model Context Protocol (MCP) Servers → "View raw config"

**Using uvx:**
```json
{
  "mcpServers": {
    "yandex-tracker": {
      "command": "uvx",
      "args": ["yandex-tracker-mcp@latest"],
      "env": {
        "TRACKER_TOKEN": "your_tracker_token_here",
        "TRACKER_CLOUD_ORG_ID": "your_cloud_org_id_here",
        "TRACKER_ORG_ID": "your_org_id_here"
      }
    }
  }
}
```

**Using Docker:**
```json
{
  "mcpServers": {
    "yandex-tracker": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "TRACKER_TOKEN",
        "-e", "TRACKER_CLOUD_ORG_ID",
        "-e", "TRACKER_ORG_ID",
        "ghcr.io/aikts/yandex-tracker-mcp:latest"
      ],
      "env": {
        "TRACKER_TOKEN": "your_tracker_token_here",
        "TRACKER_CLOUD_ORG_ID": "your_cloud_org_id_here",
        "TRACKER_ORG_ID": "your_org_id_here"
      }
    }
  }
}
```

</details>

<details>
<summary><strong>Zed</strong></summary>

**Configuration file path:**
- `~/.config/zed/settings.json`

Access via: `Cmd+,` (macOS) or `Ctrl+,` (Linux/Windows) or command palette: "zed: open settings"

**Note:** Requires Zed Preview version for MCP support.

**Using uvx:**
```json
{
  "context_servers": {
    "yandex-tracker": {
      "source": "custom",
      "command": {
        "path": "uvx",
        "args": ["yandex-tracker-mcp@latest"],
        "env": {
          "TRACKER_TOKEN": "your_tracker_token_here",
          "TRACKER_CLOUD_ORG_ID": "your_cloud_org_id_here",
          "TRACKER_ORG_ID": "your_org_id_here"
        }
      }
    }
  }
}
```

**Using Docker:**
```json
{
  "context_servers": {
    "yandex-tracker": {
      "source": "custom",
      "command": {
        "path": "docker",
        "args": [
          "run", "--rm", "-i",
          "-e", "TRACKER_TOKEN",
          "-e", "TRACKER_CLOUD_ORG_ID",
          "-e", "TRACKER_ORG_ID",
          "ghcr.io/aikts/yandex-tracker-mcp:latest"
        ],
        "env": {
          "TRACKER_TOKEN": "your_tracker_token_here",
          "TRACKER_CLOUD_ORG_ID": "your_cloud_org_id_here",
          "TRACKER_ORG_ID": "your_org_id_here"
        }
      }
    }
  }
}
```

</details>

<details>
<summary><strong>GitHub Copilot (VS Code)</strong></summary>

**Configuration file path:**
- Workspace: `.vscode/mcp.json` in your project directory
- Global: VS Code `settings.json`

**Option 1: Workspace Configuration (Recommended for security)**

Create `.vscode/mcp.json`:

**Using uvx:**
```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "tracker-token",
      "description": "Yandex Tracker Token",
      "password": true
    },
    {
      "type": "promptString",
      "id": "cloud-org-id",
      "description": "Yandex Cloud Organization ID"
    },
    {
      "type": "promptString",
      "id": "org-id",
      "description": "Yandex Tracker Organization ID (optional)"
    }
  ],
  "servers": {
    "yandex-tracker": {
      "type": "stdio",
      "command": "uvx",
      "args": ["yandex-tracker-mcp@latest"],
      "env": {
        "TRACKER_TOKEN": "${input:tracker-token}",
        "TRACKER_CLOUD_ORG_ID": "${input:cloud-org-id}",
        "TRACKER_ORG_ID": "${input:org-id}",
        "TRANSPORT": "stdio"
      }
    }
  }
}
```

**Using Docker:**
```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "tracker-token",
      "description": "Yandex Tracker Token",
      "password": true
    },
    {
      "type": "promptString",
      "id": "cloud-org-id",
      "description": "Yandex Cloud Organization ID"
    },
    {
      "type": "promptString",
      "id": "org-id",
      "description": "Yandex Tracker Organization ID (optional)"
    }
  ],
  "servers": {
    "yandex-tracker": {
      "type": "stdio",
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "TRACKER_TOKEN",
        "-e", "TRACKER_CLOUD_ORG_ID",
        "-e", "TRACKER_ORG_ID",
        "ghcr.io/aikts/yandex-tracker-mcp:latest"
      ],
      "env": {
        "TRACKER_TOKEN": "${input:tracker-token}",
        "TRACKER_CLOUD_ORG_ID": "${input:cloud-org-id}",
        "TRACKER_ORG_ID": "${input:org-id}",
        "TRANSPORT": "stdio"
      }
    }
  }
}
```

**Option 2: Global Configuration**

Add to VS Code `settings.json`:

**Using uvx:**
```json
{
  "github.copilot.chat.mcp.servers": {
    "yandex-tracker": {
      "type": "stdio",
      "command": "uvx",
      "args": ["yandex-tracker-mcp@latest"],
      "env": {
        "TRACKER_TOKEN": "your_tracker_token_here",
        "TRACKER_CLOUD_ORG_ID": "your_cloud_org_id_here",
        "TRACKER_ORG_ID": "your_org_id_here"
      }
    }
  }
}
```

**Using Docker:**
```json
{
  "github.copilot.chat.mcp.servers": {
    "yandex-tracker": {
      "type": "stdio",
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "TRACKER_TOKEN",
        "-e", "TRACKER_CLOUD_ORG_ID",
        "-e", "TRACKER_ORG_ID",
        "ghcr.io/aikts/yandex-tracker-mcp:latest"
      ],
      "env": {
        "TRACKER_TOKEN": "your_tracker_token_here",
        "TRACKER_CLOUD_ORG_ID": "your_cloud_org_id_here",
        "TRACKER_ORG_ID": "your_org_id_here"
      }
    }
  }
}
```

</details>

<details>
<summary><strong>Other MCP-Compatible Clients</strong></summary>

For other MCP-compatible clients, use the standard MCP server configuration format:

**Using uvx:**
```json
{
  "mcpServers": {
    "yandex-tracker": {
      "command": "uvx",
      "args": ["yandex-tracker-mcp@latest"],
      "env": {
        "TRACKER_TOKEN": "your_tracker_token_here",
        "TRACKER_CLOUD_ORG_ID": "your_cloud_org_id_here",
        "TRACKER_ORG_ID": "your_org_id_here"
      }
    }
  }
}
```

**Using Docker:**
```json
{
  "mcpServers": {
    "yandex-tracker": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "TRACKER_TOKEN",
        "-e", "TRACKER_CLOUD_ORG_ID",
        "-e", "TRACKER_ORG_ID",
        "ghcr.io/aikts/yandex-tracker-mcp:latest"
      ],
      "env": {
        "TRACKER_TOKEN": "your_tracker_token_here",
        "TRACKER_CLOUD_ORG_ID": "your_cloud_org_id_here",
        "TRACKER_ORG_ID": "your_org_id_here"
      }
    }
  }
}
```

</details>

**Important Notes:**
- Replace placeholder values with your actual credentials
- Restart your AI client after configuration changes
- Ensure `uvx` is installed and available in your system PATH
- For production use, consider using environment variables instead of hardcoding tokens

## Available MCP Tools

The server exposes a compact, action-based tool surface. Each tool takes an
`action` parameter so LLM clients see one tool per concept instead of 3–6
near-duplicates. Write actions are rejected when `TRACKER_READ_ONLY=true`.

For the authoritative list of actions, required parameters and return shapes,
call `list_tools` against the running server — every tool's `description`
documents its actions inline.

### Issues

- `issue_get` — read a single issue by key
- `issue_get_url` — build a Tracker web URL from an issue id
- `issues_find` — YQL search with `query` / structured `filter` / `keys` and sort
- `issues_count` — YQL match count
- `issue_get_transitions` — list the status transitions available from the current state
- `issue_create` / `issue_update` / `issue_close` / `issue_execute_transition` — write paths
- `issue_move_to_queue` — move an issue to another queue
- `issue_comments(action=get/add/update/delete)`
- `issue_links(action=get/add/delete)`
- `issue_worklogs(action=get/add/update/delete)`
- `issue_attachments(action=get/upload/download/delete)`
- `issue_checklist(action=get/add/update/delete/clear)`
- `issue_tags(action=add/remove)`

### Queues & reference data

- `queues(action=list/tags/versions/fields/metadata/create)`
- `tracker_reference(kind=global_fields/statuses/issue_types/priorities/resolutions)`

### Boards, sprints, agile

- `boards(action=list/get/columns/sprints/create/update/delete)`
- `board_columns(action=create/update/delete)`
- `sprints(action=get/create/update/delete/start/finish)`

### Entities & saved views

- `components(action=list/get/create/update/delete)`
- `filters(action=list/get/create/update/delete)`
- `dashboards(action=list/get/widgets/create/update/delete)`

### Automations

- `triggers(action=list/get/create/update/delete)`
- `autoactions(action=list/get/create/update/delete)`
- `macros(action=list/get/create/update/delete)`
- `workflows(action=list/get_queue)`

### Users

- `users(action=list/search/get/current)`

### Projects / portfolios / goals

- `projects_search`, `portfolios_search`, `goals_search`, `projects_legacy_list`
- `entity_get` / `entity_create` / `entity_update` / `entity_delete`

### Bulk operations

- `bulk(action=update/move/transition/status)`


## http Transport

The MCP server can also be run in streamable-http mode for web-based integrations or when stdio transport is not suitable.

### streamable-http Mode Environment Variables

```env
# Required - Set transport to streamable-http mode
TRANSPORT=streamable-http

# Server Configuration
HOST=0.0.0.0  # Default: 0.0.0.0 (all interfaces)
PORT=8000     # Default: 8000
```

### Starting the streamable-http Server

```bash
# Basic streamable-http server startup
TRANSPORT=streamable-http uvx yandex-tracker-mcp@latest

# With custom host and port
TRANSPORT=streamable-http \
HOST=localhost \
PORT=9000 \
uvx yandex-tracker-mcp@latest

# With all environment variables
TRANSPORT=streamable-http \
HOST=0.0.0.0 \
PORT=8000 \
TRACKER_TOKEN=your_token \
TRACKER_CLOUD_ORG_ID=your_org_id \
uvx yandex-tracker-mcp@latest
```

You may omit the server-wide `TRACKER_CLOUD_ORG_ID` or `TRACKER_ORG_ID` when
the organization identifier is supplied in the MCP URL configured in Codex:

```bash
codex mcp add yandex-tracker --url "http://localhost:8000/mcp/?cloudOrgId=your_cloud_org_id"
```

or

```bash
codex mcp add yandex-tracker --url "http://localhost:8000/mcp/?orgId=your_org_id"
```

You may also skip configuring global `TRACKER_TOKEN` environment variable if you choose to use OAuth 2.0 authentication (see below).

### OAuth 2.0 Authentication

The Yandex Tracker MCP Server supports OAuth 2.0 authentication as a secure alternative to static API tokens. When configured, the server acts as an OAuth provider, facilitating authentication between your MCP client and Yandex OAuth services.

#### How OAuth Works

The MCP server implements a standard OAuth 2.0 authorization code flow:

1. **Client Registration**: Your MCP client registers with the server to obtain client credentials
2. **Authorization**: Users are redirected to Yandex OAuth to authenticate
3. **Token Exchange**: The server exchanges authorization codes for access tokens
4. **API Access**: Clients use bearer tokens for all API requests
5. **Token Refresh**: Expired tokens can be refreshed without re-authentication

```
MCP Client → MCP Server → Yandex OAuth → User Authentication
    ↑                                           ↓
    └────────── Access Token ←─────────────────┘
```

#### OAuth Configuration

To enable OAuth authentication, set the following environment variables:

```env
# Enable OAuth mode
OAUTH_ENABLED=true

# Yandex OAuth Application Credentials (required for OAuth)
OAUTH_CLIENT_ID=your_yandex_oauth_app_id
OAUTH_CLIENT_SECRET=your_yandex_oauth_app_secret

# Public URL of your MCP server (required for OAuth callbacks)
MCP_SERVER_PUBLIC_URL=https://your-mcp-server.example.com

# Optional OAuth settings
OAUTH_SERVER_URL=https://oauth.yandex.ru  # Default Yandex OAuth server

# When OAuth is enabled, TRACKER_TOKEN becomes optional
```

#### Setting Up Yandex OAuth Application

1. Go to [Yandex OAuth](https://oauth.yandex.ru/) and create a new application
2. Set the callback URL to: `{MCP_SERVER_PUBLIC_URL}/oauth/yandex/callback`
3. Request the following permissions:
   - `tracker:read` - Read permissions for Tracker
   - `tracker:write` - Write permissions for Tracker
4. Save your Client ID and Client Secret

#### OAuth vs Static Token Authentication

| Feature          | OAuth                          | Static Token               |
|------------------|--------------------------------|----------------------------|
| Security         | Dynamic tokens with expiration | Long-lived static tokens   |
| User Experience  | Interactive login flow         | One-time configuration     |
| Token Management | Automatic refresh              | Manual rotation            |
| Access Control   | Per-user authentication        | Shared token               |
| Setup Complexity | Requires OAuth app setup       | Simple token configuration |

#### OAuth Mode Limitations

- Currently, the OAuth mode requires the MCP server to be publicly accessible for callback URLs
- OAuth mode is best suited for interactive clients that support web-based authentication flows

#### Using OAuth with MCP Clients

When OAuth is enabled, MCP clients will need to:
1. Support OAuth 2.0 authorization code flow
2. Handle token refresh when access tokens expire
3. Store refresh tokens securely for persistent authentication

**Note**: Not all MCP clients currently support OAuth authentication. Check your client's documentation for OAuth compatibility.

Example configuration for Codex:

```bash
codex mcp add yandex-tracker --url https://your-mcp-server.example.com/mcp/
codex mcp login yandex-tracker
```

#### OAuth Data Storage

The MCP server supports two different storage backends for OAuth data (client registrations, access tokens, refresh tokens, and authorization states):

##### InMemory Store (Default)

The in-memory store keeps all OAuth data in server memory. This is the default option and requires no additional configuration.

**Characteristics:**
- **Persistence**: Data is lost when the server restarts
- **Performance**: Very fast access since data is stored in memory
- **Scalability**: Limited to single server instance
- **Setup**: No additional dependencies required
- **Best for**: Development, testing, or single-instance deployments where losing OAuth sessions on restart is acceptable

**Configuration:**
```env
OAUTH_STORE=memory  # Default value, can be omitted
```

##### Redis Store

The Redis store provides persistent storage for OAuth data using a Redis database. This ensures OAuth sessions survive server restarts and enables multi-instance deployments.

**Characteristics:**
- **Persistence**: Data persists across server restarts
- **Performance**: Fast access with network overhead
- **Scalability**: Supports multiple server instances sharing the same Redis database
- **Setup**: Requires Redis server installation and configuration
- **Best for**: Production deployments, high availability setups, or when OAuth sessions must persist

**Configuration:**
```env
# Enable Redis store for OAuth data
OAUTH_STORE=redis

# Redis connection settings (same as used for tools caching)
REDIS_ENDPOINT=localhost                  # Default: localhost
REDIS_PORT=6379                           # Default: 6379
REDIS_DB=0                                # Default: 0
REDIS_PASSWORD=your_redis_password        # Optional: Redis password
REDIS_POOL_MAX_SIZE=10                    # Default: 10
```

**Storage Behavior:**
- **Client Information**: Stored persistently
- **OAuth States**: Stored with TTL (time-to-live) for security
- **Authorization Codes**: Stored with TTL and automatically cleaned up after use
- **Access Tokens**: Stored with automatic expiration based on token lifetime
- **Refresh Tokens**: Stored persistently until revoked
- **Key Namespacing**: Uses `oauth:*` prefixes to avoid conflicts with other Redis data

##### Token Encryption (Required for Redis Store)

When using Redis store, you must configure encryption to protect OAuth tokens at rest. Token values are encrypted using Fernet (AES-128) and Redis keys use SHA-256 hashes instead of raw tokens, preventing token exposure if Redis is compromised.

**Generate an encryption key:**
```bash
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

**Configuration:**
```env
# Single encryption key
OAUTH_ENCRYPTION_KEYS=<base64-encoded-32-byte-key>

# Multiple keys for rotation (first encrypts, all decrypt)
OAUTH_ENCRYPTION_KEYS=<new-key>,<old-key>
```

Key rotation allows seamless key updates: add the new key first, wait for old tokens to expire, then remove the old key.

**Important Notes:**
- Both stores use the same Redis connection settings as the tools caching system
- When using Redis store, ensure your Redis instance is properly secured and accessible
- The `OAUTH_STORE` setting only affects OAuth data storage; tools caching uses `TOOLS_CACHE_ENABLED`
- Redis store uses JSON serialization for better cross-language compatibility and debugging

## Authentication

Yandex Tracker MCP Server supports multiple authentication methods with a clear priority order. The server will use the first available authentication method based on this hierarchy:

### Authentication Priority Order

1. **Dynamic OAuth Token** (highest priority)
   - When OAuth is enabled and a user authenticates via OAuth flow
   - Tokens are dynamically obtained and refreshed per user session
   - Supports both standard Yandex OAuth and Yandex Cloud federative OAuth
   - Required env vars: `OAUTH_ENABLED=true`, `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `MCP_SERVER_PUBLIC_URL`
   - Additional vars for federative OAuth: `OAUTH_SERVER_URL=https://auth.yandex.cloud/oauth`, `OAUTH_TOKEN_TYPE=Bearer`, `OAUTH_USE_SCOPES=false`

2. **Static OAuth Token**
   - Traditional OAuth token provided via environment variable
   - Single token used for all requests
   - Required env var: `TRACKER_TOKEN` (your OAuth token)

3. **Static IAM Token**
   - IAM (Identity and Access Management) token for service-to-service authentication
   - Suitable for automated systems and CI/CD pipelines
   - Required env var: `TRACKER_IAM_TOKEN` (your IAM token)

4. **Dynamic IAM Token** (lowest priority)
   - Automatically retrieved using service account credentials
   - Token is fetched and refreshed automatically
   - Required env vars: `TRACKER_SA_KEY_ID`, `TRACKER_SA_SERVICE_ACCOUNT_ID`, `TRACKER_SA_PRIVATE_KEY`

### Authentication Scenarios

#### Scenario 1: OAuth with Dynamic Tokens (Recommended for Interactive Use)
```env
# Enable OAuth mode
OAUTH_ENABLED=true
OAUTH_CLIENT_ID=your_oauth_app_id
OAUTH_CLIENT_SECRET=your_oauth_app_secret
MCP_SERVER_PUBLIC_URL=https://your-server.com

# Organization ID (choose one)
TRACKER_CLOUD_ORG_ID=your_cloud_org_id  # or TRACKER_ORG_ID
```

#### Scenario 2: Static OAuth Token (Simple Setup)
```env
# OAuth token
TRACKER_TOKEN=your_oauth_token

# Organization ID (choose one)
TRACKER_CLOUD_ORG_ID=your_cloud_org_id  # or TRACKER_ORG_ID
```

#### Scenario 3: Static IAM Token
```env
# IAM token
TRACKER_IAM_TOKEN=your_iam_token

# Organization ID (choose one)
TRACKER_CLOUD_ORG_ID=your_cloud_org_id  # or TRACKER_ORG_ID
```

#### Scenario 4: Dynamic IAM Token with Service Account
```env
# Service account credentials
TRACKER_SA_KEY_ID=your_key_id
TRACKER_SA_SERVICE_ACCOUNT_ID=your_service_account_id
TRACKER_SA_PRIVATE_KEY=your_private_key

# Organization ID (choose one)
TRACKER_CLOUD_ORG_ID=your_cloud_org_id  # or TRACKER_ORG_ID
```

#### Scenario 5: Federative OAuth for OIDC Applications (Advanced)
```env
# Enable OAuth with Yandex Cloud federation
OAUTH_ENABLED=true
OAUTH_SERVER_URL=https://auth.yandex.cloud/oauth
OAUTH_TOKEN_TYPE=Bearer
OAUTH_USE_SCOPES=false
OAUTH_CLIENT_ID=your_oidc_client_id
OAUTH_CLIENT_SECRET=your_oidc_client_secret
MCP_SERVER_PUBLIC_URL=https://your-server.com

# Organization ID (choose one)
TRACKER_CLOUD_ORG_ID=your_cloud_org_id  # or TRACKER_ORG_ID
```

This configuration enables authentication through [Yandex Cloud OIDC applications](https://yandex.cloud/ru/docs/organization/operations/applications/oidc-create), which is required for [federated accounts](https://yandex.cloud/ru/docs/organization/operations/manage-federations) in Yandex Cloud. Federated users authenticate through their organization's identity provider (IdP) and use this OAuth flow to access Yandex Tracker APIs.

### Important Notes

- The server checks authentication methods in the order listed above
- Only one authentication method will be used at a time
- For production use, dynamic tokens (OAuth or IAM) are recommended for better security
- IAM tokens have a shorter lifetime than OAuth tokens and may need more frequent renewal
- When using service accounts, ensure the account has appropriate permissions for Yandex Tracker

## Configuration

### Environment Variables

```env
# Authentication (use one of the following methods)
# Method 1: OAuth Token
TRACKER_TOKEN=your_yandex_tracker_oauth_token

# Method 2: IAM Token
TRACKER_IAM_TOKEN=your_iam_token

# Method 3: Service Account (for dynamic IAM token)
TRACKER_SA_KEY_ID=your_key_id                    # Service account key ID
TRACKER_SA_SERVICE_ACCOUNT_ID=your_sa_id        # Service account ID
TRACKER_SA_PRIVATE_KEY=your_private_key          # Service account private key

# Organization Configuration (choose one)
TRACKER_CLOUD_ORG_ID=your_cloud_org_id    # For Yandex Cloud organizations
TRACKER_ORG_ID=your_org_id                # For Yandex 360 organizations

# API Configuration (optional)
TRACKER_API_BASE_URL=https://api.tracker.yandex.net  # Default: https://api.tracker.yandex.net
TRACKER_HTTP_TIMEOUT=30                   # Default: 30s total per request (raise for large attachments)
TRACKER_GET_RETRIES=2                     # Default: 2 retries for GETs on 429/502/503/504

# Security - Restrict access to specific queues (optional)
TRACKER_LIMIT_QUEUES=PROJ1,PROJ2,DEV      # Comma-separated queue keys

# Issue-response tuning (optional)
TRACKER_HIDE_ISSUE_FIELDS=favorite,qaEngineer  # Default: favorite,qaEngineer. Empty string = keep everything.

# Remote-URL attachment uploads (optional, disabled by default)
# Enables `issue_attachments(action="upload", source_url="https://...")`
TRACKER_ATTACHMENT_URL_ALLOWED_DOMAINS=files.example.com,*.cdn.example.com  # Required to enable
TRACKER_ATTACHMENT_URL_MAX_BYTES=52428800          # Default: 50 MiB
TRACKER_ATTACHMENT_URL_TIMEOUT_SECONDS=30          # Default: 30s

# Server Configuration
HOST=0.0.0.0                              # Default: 0.0.0.0
PORT=8000                                 # Default: 8000
TRANSPORT=stdio                           # Options: stdio, streamable-http, sse

# Redis connection settings (used for caching and OAuth store)
REDIS_ENDPOINT=localhost                  # Default: localhost
REDIS_PORT=6379                           # Default: 6379
REDIS_DB=0                                # Default: 0
REDIS_PASSWORD=your_redis_password        # Optional: Redis password
REDIS_POOL_MAX_SIZE=10                    # Default: 10

# Tools caching configuration (optional)
TOOLS_CACHE_ENABLED=true                  # Default: false
TOOLS_CACHE_REDIS_TTL=3600                # Default: 3600 seconds (1 hour)

# OAuth 2.0 Authentication (optional)
OAUTH_ENABLED=true                        # Default: false
OAUTH_STORE=redis                         # Options: memory, redis (default: memory)
OAUTH_SERVER_URL=https://oauth.yandex.ru  # Default: https://oauth.yandex.ru (use https://auth.yandex.cloud/oauth for federation)
OAUTH_TOKEN_TYPE=<Bearer|OAuth|<empty>>   # Default: <empty> (required to be Bearer for Yandex Cloud federation)
OAUTH_USE_SCOPES=true                     # Default: true (set to false for Yandex Cloud federation)
OAUTH_CLIENT_ID=your_oauth_client_id      # Required when OAuth enabled
OAUTH_CLIENT_SECRET=your_oauth_secret     # Required when OAuth enabled
MCP_SERVER_PUBLIC_URL=https://your.server.com  # Required when OAuth enabled
TRACKER_READ_ONLY=true                    # Default: false - Limit OAuth to read-only permissions
```

## Docker Deployment

### Using Pre-built Image (Recommended)

```bash
# Using environment file
docker run --env-file .env -p 8000:8000 ghcr.io/aikts/yandex-tracker-mcp:latest

# With inline environment variables
docker run -e TRACKER_TOKEN=your_token \
           -e TRACKER_CLOUD_ORG_ID=your_org_id \
           -p 8000:8000 \
           ghcr.io/aikts/yandex-tracker-mcp:latest
```

### Building the Image Locally

```bash
docker build -t yandex-tracker-mcp .
```

### Docker Compose

**Using pre-built image:**
```yaml
version: '3.8'
services:
  mcp-tracker:
    image: ghcr.io/aikts/yandex-tracker-mcp:latest
    ports:
      - "8000:8000"
    environment:
      - TRACKER_TOKEN=${TRACKER_TOKEN}
      - TRACKER_CLOUD_ORG_ID=${TRACKER_CLOUD_ORG_ID}
```

**Building locally:**
```yaml
version: '3.8'
services:
  mcp-tracker:
    build: .
    ports:
      - "8000:8000"
    environment:
      - TRACKER_TOKEN=${TRACKER_TOKEN}
      - TRACKER_CLOUD_ORG_ID=${TRACKER_CLOUD_ORG_ID}
```

### Development Setup

```bash
# Clone and setup
git clone https://github.com/aikts/yandex-tracker-mcp
cd yandex-tracker-mcp

# Install development dependencies
uv sync --dev

# Formatting and static checking
task
```

## License

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.

## Support

For issues and questions:
- Review Yandex Tracker API documentation
- Submit issues at https://github.com/aikts/yandex-tracker-mcp/issues
