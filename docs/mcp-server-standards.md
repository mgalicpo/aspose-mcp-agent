# MCP Server Standards

Standards for building Aspose MCP servers that are MCP protocol-compliant
and meet [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) listing quality.

---

## MCP Protocol Requirements

### Tool Registration

Every tool MUST have:
- `name` — lowercase, underscore-separated (e.g. `zip_create`, `font_convert`)
- `description` — clear, concise, what it does
- `[Description]` attribute on every parameter

```csharp
[McpServerTool(Name = "zip_create")]
[Description("Create a ZIP archive from files or directories.")]
public static string Create(
    [Description("Output ZIP file path")] string outputPath,
    [Description("Source file or directory paths")] string[] sourcePaths)
```

### Transport Rules

- **STDIO transport**: NEVER write to stdout — it breaks JSON-RPC. Use `Console.Error.WriteLine` for all logs.
- `Program.cs` must use `.WithStdioServerTransport()`
- All logging must go through `builder.Logging.AddConsole` with `LogToStandardErrorThreshold = Trace`

### Error Contract

All tools return structured JSON — never raw exceptions:

```json
{ "success": true,  "data":  { ... } }
{ "success": false, "error": { "code": "INVALID_INPUT", "message": "..." } }
```

Rules:
- Always catch exceptions and return `Error("CODE", ex.Message)`
- Never expose file system paths in error messages
- Never log license data, API keys, or secrets
- Error codes: `INVALID_INPUT`, `SOURCE_NOT_FOUND`, `ARCHIVE_NOT_FOUND`, `<ACTION>_FAILED`

### Security

- Validate inputs before calling Aspose API (null/empty checks, file existence)
- Never log `ASPOSE_LICENSE_PATH` value or license content
- Sanitize file paths in error messages
- Support evaluation mode: server must work without a license (with watermarks)

---

## Licensing Pattern

Every server loads the license via `ASPOSE_LICENSE_PATH` env var using a stream:

```csharp
var licensePath = Environment.GetEnvironmentVariable("ASPOSE_LICENSE_PATH");
if (!string.IsNullOrWhiteSpace(licensePath) && File.Exists(licensePath))
{
    using var stream = File.OpenRead(licensePath);
    new License().SetLicense(stream);
}
```

Graceful fallback: if env var is not set, log to stderr and continue in evaluation mode.

---

## Repo Structure (required)

```
aspose-<product>-mcp/
├── src/<Product>Mcp.Server/
│   ├── <Product>Mcp.Server.csproj
│   ├── Program.cs
│   ├── Licensing.cs
│   └── Tools/
│       └── <Product>Tools.cs
├── tests/<Product>Mcp.Tests/
│   ├── <Product>Mcp.Tests.csproj
│   └── <Product>ToolsTests.cs
├── fixtures/              # test assets (sample files)
├── tool-map.md            # Aspose docs section → MCP tool mapping
├── README.md              # English, all 8 sections (see below)
├── LICENSE                # MIT
├── .gitignore
└── .github/
    ├── workflows/ci.yml
    └── dependabot.yml
```

Use `python scripts/new_product.py` to scaffold this structure automatically.

---

## README Template (8 required sections)

### 1. Header + badges
```markdown
# aspose-<product>-mcp
MCP server for Aspose.<Product> .NET SDK — [brief feature list]
```

### 2. Prerequisites
- .NET 8.0 SDK
- Aspose.<Product> license (optional — evaluation mode available)

### 3. Installation
```bash
git clone https://github.com/org/aspose-<product>-mcp
cd aspose-<product>-mcp
dotnet restore && dotnet build
```

### 4. Configuration
```
ASPOSE_LICENSE_PATH=/path/to/Aspose.License.lic   # optional
```

### 5. Tool listing (table)
| Tool | Description | Key Parameters |
|---|---|---|
| `<slug>_<action>` | What it does | param1, param2 |

### 6. Usage examples (JSON tool calls)
```json
{
  "tool": "zip_create",
  "arguments": { "outputPath": "archive.zip", "sourcePaths": ["file.txt"] }
}
```

### 7. Client configurations

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "aspose-<product>": {
      "command": "dotnet",
      "args": ["run", "--project", "src/<Product>Mcp.Server"]
    }
  }
}
```

**Claude Code**:
```bash
claude mcp add aspose-<product> -- dotnet run --project src/<Product>Mcp.Server
```

### 8. License
MIT for the MCP server code. Aspose SDK requires a separate commercial license for production use.

---

## awesome-mcp-servers Listing Format

Single line, alphabetically sorted in category `🛠️ Other Tools and Integrations`:

```
* [org/aspose-<product>-mcp](https://github.com/org/aspose-<product>-mcp) #️⃣ 🏠 🪟 🐧 🍎 - Brief description.
```

**Required icons:**
- `#️⃣` — C# codebase
- `🏠` — local processing (no remote API calls)
- `☁️` — calls a remote API
- `🪟 🐧 🍎` — supported OS platforms (Windows, Linux, macOS)

---

## Quality Checklist

Before any MCP server is considered done:

- [ ] `dotnet build` succeeds with 0 warnings
- [ ] `dotnet test` — all tests green
- [ ] Server starts and lists all tools (`dotnet run` + MCP Inspector)
- [ ] Each tool has `[Description]` on method and all parameters
- [ ] Error handling returns structured JSON (`success: false, error: {code, message}`)
- [ ] No secrets or license data in any output
- [ ] Works without Aspose license (evaluation mode — watermarks OK)
- [ ] README has all 8 sections
- [ ] `tool-map.md` maps Aspose docs sections to tools
- [ ] CI workflow exists and passes (`.github/workflows/ci.yml`)
- [ ] `.gitignore` excludes `bin/`, `obj/`, `*.lic`, `.env`, `.claude/`
- [ ] Dependabot configured for weekly NuGet updates
