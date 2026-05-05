#!/usr/bin/env python3
"""
Scaffold a new Aspose MCP server project from template.

Creates the full project structure (src, tests, CI, .gitignore, tool-map.md),
optionally creates a GitHub repo and pushes, then registers the product in
products.json for automatic version tracking.

Usage:
  python scripts/new_product.py --slug words --nuget "Aspose.Words" --version "25.1.0" \\
      --output-dir "D:\\GIT\\FinishedMCPservers"

  python scripts/new_product.py --slug words --nuget "Aspose.Words" --version "25.1.0" \\
      --output-dir "D:\\GIT\\FinishedMCPservers" --github-user mgalicpo --create-repo
"""
import argparse
import json
import os
import subprocess
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTS_FILE = os.path.join(REPO_ROOT, "products.json")

MCP_VERSION  = "0.8.0-preview.1"
HOST_VERSION = "10.0.3"


# ── Name helpers ──────────────────────────────────────────────────────────────

def names(slug: str):
    """Return all naming variants derived from the slug."""
    cap    = slug.capitalize()           # words → Words
    prefix = f"{cap}Mcp"                # WordsMcp
    return {
        "slug":       slug,             # words
        "cap":        cap,              # Words
        "prefix":     prefix,           # WordsMcp
        "server_ns":  f"{prefix}.Server",  # WordsMcp.Server
        "tests_ns":   f"{prefix}.Tests",   # WordsMcp.Tests
        "solution":   f"Aspose{prefix}",   # AsposeWordsMcp
        "repo":       f"aspose-{slug}-mcp",# aspose-words-mcp
        "server_dir": f"src/{prefix}.Server",
        "tests_dir":  f"tests/{prefix}.Tests",
    }


# ── File templates ────────────────────────────────────────────────────────────

def t_server_csproj(n, nuget, version):
    return f"""\
<Project Sdk="Microsoft.NET.Sdk">

  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="{nuget}" Version="{version}" />
    <PackageReference Include="Microsoft.Extensions.Hosting" Version="{HOST_VERSION}" />
    <PackageReference Include="ModelContextProtocol" Version="{MCP_VERSION}" />
  </ItemGroup>

</Project>
"""

def t_program(n, nuget):
    return f"""\
using {n['server_ns']};
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

Licensing.Apply();

var builder = Host.CreateApplicationBuilder(args);

builder.Logging.AddConsole(opts =>
{{
    opts.LogToStandardErrorThreshold = Microsoft.Extensions.Logging.LogLevel.Trace;
}});

builder.Services
    .AddMcpServer()
    .WithStdioServerTransport()
    .WithToolsFromAssembly();

await builder.Build().RunAsync();
"""

def t_licensing(n, nuget):
    return f"""\
using {nuget};

namespace {n['server_ns']};

internal static class Licensing
{{
    public static void Apply()
    {{
        var licensePath = Environment.GetEnvironmentVariable("ASPOSE_LICENSE_PATH");
        Console.Error.WriteLine($"[{nuget}] ASPOSE_LICENSE_PATH = '{{licensePath ?? "(not set)"}}'");

        if (string.IsNullOrWhiteSpace(licensePath))
        {{
            Console.Error.WriteLine("[{nuget}] No license configured — running in evaluation mode.");
            return;
        }}

        if (!File.Exists(licensePath))
        {{
            Console.Error.WriteLine($"[{nuget}] License file not found at: {{licensePath}}");
            return;
        }}

        try
        {{
            using var stream = File.OpenRead(licensePath);
            var license = new License();
            license.SetLicense(stream);
            Console.Error.WriteLine("[{nuget}] License applied successfully.");
        }}
        catch (Exception ex)
        {{
            Console.Error.WriteLine($"[{nuget}] Failed to apply license: {{ex.Message}}");
        }}
    }}
}}
"""

def t_tools_stub(n, nuget):
    return f"""\
using System.ComponentModel;
using System.Text.Json;
using ModelContextProtocol.Server;

namespace {n['server_ns']}.Tools;

// TODO: implement tools for {nuget}
// See docs/new-product-analysis-template.md for the analysis workflow.
// Each tool follows this pattern:
//
//   [McpServerTool(Name = "{n['slug']}_<action>")]
//   [Description("What this tool does")]
//   public static string <Action>(
//       [Description("param description")] string param)
//   {{
//       try
//       {{
//           // validate inputs
//           // call Aspose API
//           return Success(new {{ result }});
//       }}
//       catch (Exception ex)
//       {{
//           return Error("ACTION_FAILED", ex.Message);
//       }}
//   }}

[McpServerToolType]
public static class {n['cap']}Tools
{{
    private static string Success(object data) =>
        JsonSerializer.Serialize(new {{ success = true, data }});

    private static string Error(string code, string message) =>
        JsonSerializer.Serialize(new {{ success = false, error = new {{ code, message }} }});
}}
"""

def t_tests_csproj(n):
    return f"""\
<Project Sdk="Microsoft.NET.Sdk">

  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <IsPackable>false</IsPackable>
    <IsTestProject>true</IsTestProject>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="coverlet.collector" Version="6.0.0" />
    <PackageReference Include="FluentAssertions" Version="8.8.0" />
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
    <PackageReference Include="xunit" Version="2.5.3" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.5.3" />
  </ItemGroup>

  <ItemGroup>
    <Using Include="Xunit" />
  </ItemGroup>

  <ItemGroup>
    <ProjectReference Include="..\\..\\{n['server_dir']}\\{n['prefix']}.Server.csproj" />
  </ItemGroup>

</Project>
"""

def t_tests_stub(n):
    return f"""\
using {n['server_ns']}.Tools;
using System.Text.Json;

namespace {n['tests_ns']};

// TODO: add tests for each tool.
// Pattern:
//
// public class {n['cap']}ToolsTests : IDisposable
// {{
//     private readonly string _tempDir = Path.Combine(Path.GetTempPath(), $"test_{{Guid.NewGuid():N}}");
//
//     public {n['cap']}ToolsTests() => Directory.CreateDirectory(_tempDir);
//     public void Dispose() => Directory.Delete(_tempDir, true);
//
//     [Fact]
//     public void SomeOperation_ValidInput_Succeeds()
//     {{
//         var result = {n['cap']}Tools.SomeMethod(...);
//         var json = JsonSerializer.Deserialize<JsonElement>(result);
//         Assert.True(json.GetProperty("success").GetBoolean(), result);
//     }}
// }}
"""

def t_sln(n):
    src_folder_guid  = str(uuid.uuid4()).upper()
    test_folder_guid = str(uuid.uuid4()).upper()
    server_guid      = str(uuid.uuid4()).upper()
    tests_guid       = str(uuid.uuid4()).upper()
    return f"""\
Microsoft Visual Studio Solution File, Format Version 12.00
# Visual Studio Version 17
VisualStudioVersion = 17.0.31903.59
MinimumVisualStudioVersion = 10.0.40219.1
Project("{{2150E333-8FDC-42A3-9474-1A3956D46DE8}}") = "src", "src", "{{{src_folder_guid}}}"
EndProject
Project("{{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}}") = "{n['prefix']}.Server", "{n['server_dir']}\\{n['prefix']}.Server.csproj", "{{{server_guid}}}"
EndProject
Project("{{2150E333-8FDC-42A3-9474-1A3956D46DE8}}") = "tests", "tests", "{{{test_folder_guid}}}"
EndProject
Project("{{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}}") = "{n['prefix']}.Tests", "{n['tests_dir']}\\{n['prefix']}.Tests.csproj", "{{{tests_guid}}}"
EndProject
Global
	GlobalSection(SolutionConfigurationPlatforms) = preSolution
		Debug|Any CPU = Debug|Any CPU
		Release|Any CPU = Release|Any CPU
	EndGlobalSection
	GlobalSection(ProjectConfigurationPlatforms) = postSolution
		{{{server_guid}}}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
		{{{server_guid}}}.Debug|Any CPU.Build.0 = Debug|Any CPU
		{{{server_guid}}}.Release|Any CPU.ActiveCfg = Release|Any CPU
		{{{server_guid}}}.Release|Any CPU.Build.0 = Release|Any CPU
		{{{tests_guid}}}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
		{{{tests_guid}}}.Debug|Any CPU.Build.0 = Debug|Any CPU
		{{{tests_guid}}}.Release|Any CPU.ActiveCfg = Release|Any CPU
		{{{tests_guid}}}.Release|Any CPU.Build.0 = Release|Any CPU
	EndGlobalSection
	GlobalSection(SolutionProperties) = preSolution
		HideSolutionNode = FALSE
	EndGlobalSection
	GlobalSection(NestedProjects) = preSolution
		{{{server_guid}}} = {{{src_folder_guid}}}
		{{{tests_guid}}} = {{{test_folder_guid}}}
	EndGlobalSection
EndGlobal
"""

def t_gitignore():
    return """\
bin/
obj/
.vs/
*.user
.idea/
*.local
.env
*.lic
Aspose*.lic
TestResults/
coverage/
.DS_Store
Thumbs.db
.claude/
"""

def t_ci(n):
    return f"""\
name: CI

on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '8.0.x'
      - run: dotnet restore
      - run: dotnet build --no-restore --configuration Release
      - run: dotnet test --no-build --configuration Release --verbosity normal
"""

def t_dependabot(n):
    return f"""\
version: 2
updates:
  - package-ecosystem: nuget
    directory: /
    schedule:
      interval: weekly
"""

def t_tool_map(n, nuget):
    return f"""\
# Tool Map — {nuget} MCP Server

Maps {nuget} Developer Guide sections to MCP tools exposed by this server.

| Doc Section | Tool Name | Description |
|---|---|---|
| TODO | `{n['slug']}_<action>` | TODO |

## Reference

- Developer Guide: https://docs.aspose.com/{n['slug']}/net/developer-guide/
- API Reference: https://reference.aspose.com/{n['slug']}/net/
- GitHub Examples: https://github.com/aspose-{n['slug']}/Aspose.{n['cap']}-for-.NET
"""

def t_readme(n, nuget, version):
    return f"""\
# {n['repo']}

MCP server for {nuget} .NET SDK.

## Prerequisites

- .NET 8.0 SDK
- {nuget} license (optional — evaluation mode available)

## Installation

```bash
git clone https://github.com/YOUR_USER/{n['repo']}
cd {n['repo']}
dotnet restore
dotnet build
```

## Configuration

```
ASPOSE_LICENSE_PATH=/path/to/license.lic   # optional
```

## Tools

| Tool | Description |
|---|---|
| *(implement tools — see tool-map.md)* | |

## Usage

**Claude Desktop** (`claude_desktop_config.json`):
```json
{{
  "mcpServers": {{
    "{n['repo']}": {{
      "command": "dotnet",
      "args": ["run", "--project", "{n['server_dir']}"]
    }}
  }}
}}
```

**Claude Code**:
```bash
claude mcp add {n['repo']} -- dotnet run --project {n['server_dir']}
```

## License

MIT — see [LICENSE](LICENSE).
{nuget} SDK requires a separate commercial license for production use.
"""

def t_license():
    return """\
MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


# ── File writer ───────────────────────────────────────────────────────────────

def write(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  created: {os.path.relpath(path)}")


# ── Scaffold ──────────────────────────────────────────────────────────────────

def scaffold(n: dict, nuget: str, version: str, output_dir: str):
    root = os.path.join(output_dir, n["repo"])

    if os.path.exists(root):
        print(f"ERROR: Directory already exists: {root}")
        return None

    print(f"\nScaffolding {n['repo']} in {output_dir}...")

    # Solution
    write(os.path.join(root, f"{n['solution']}.sln"), t_sln(n))

    # Server project
    sd = os.path.join(root, n["server_dir"])
    write(os.path.join(sd, f"{n['prefix']}.Server.csproj"), t_server_csproj(n, nuget, version))
    write(os.path.join(sd, "Program.cs"),  t_program(n, nuget))
    write(os.path.join(sd, "Licensing.cs"), t_licensing(n, nuget))
    write(os.path.join(sd, "Tools", f"{n['cap']}Tools.cs"), t_tools_stub(n, nuget))

    # Tests project
    td = os.path.join(root, n["tests_dir"])
    write(os.path.join(td, f"{n['prefix']}.Tests.csproj"), t_tests_csproj(n))
    write(os.path.join(td, f"{n['cap']}ToolsTests.cs"), t_tests_stub(n))

    # Root files
    write(os.path.join(root, ".gitignore"),  t_gitignore())
    write(os.path.join(root, "tool-map.md"), t_tool_map(n, nuget))
    write(os.path.join(root, "README.md"),   t_readme(n, nuget, version))
    write(os.path.join(root, "LICENSE"),     t_license())
    write(os.path.join(root, ".github", "workflows", "ci.yml"), t_ci(n))
    write(os.path.join(root, ".github", "dependabot.yml"),      t_dependabot(n))
    os.makedirs(os.path.join(root, "fixtures"), exist_ok=True)

    return root


# ── Git + GitHub ──────────────────────────────────────────────────────────────

def run(cmd: list[str], cwd: str):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}: {result.stderr.strip()}")
    return result.stdout.strip()


def git_init_and_push(root: str, n: dict, github_user: str):
    print("\nInitialising git...")
    run(["git", "init", "-b", "main"], cwd=root)
    run(["git", "add", "-A"], cwd=root)
    run(["git", "commit", "-m", f"feat: initial scaffold for {n['repo']}"], cwd=root)

    print("Creating GitHub repo...")
    run(["gh", "repo", "create", n["repo"], "--private",
         "--description", f"MCP server for Aspose.{n['cap']} .NET"], cwd=root)

    remote = f"https://github.com/{github_user}/{n['repo']}.git"
    run(["git", "remote", "add", "origin", remote], cwd=root)
    run(["git", "push", "-u", "origin", "main"], cwd=root)
    print(f"  Pushed to {remote}")
    return f"{github_user}/{n['repo']}"


# ── products.json ─────────────────────────────────────────────────────────────

def register_product(n: dict, nuget: str, version: str, github_repo: str | None):
    with open(PRODUCTS_FILE) as f:
        config = json.load(f)

    existing = [p for p in config["products"] if p["slug"] == n["slug"]]
    if existing:
        print(f"\nproducts.json: '{n['slug']}' already registered — skipping.")
        return

    entry = {
        "name":            n["repo"],
        "display":         f"Aspose.{n['cap']}",
        "nuget":           nuget,
        "slug":            n["slug"],
        "current_version": version,
    }
    if github_repo:
        entry["github_repo"] = github_repo

    config["products"].append(entry)
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(config, f, indent=2)
    print(f"\nproducts.json: registered '{n['slug']}' at {version}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scaffold a new Aspose MCP server project"
    )
    parser.add_argument("--slug",        required=True, help="Product slug, lowercase (e.g. words, imaging)")
    parser.add_argument("--nuget",       required=True, help="NuGet package name (e.g. Aspose.Words)")
    parser.add_argument("--version",     required=True, help="Initial NuGet version (e.g. 25.1.0)")
    parser.add_argument("--output-dir",  required=True, help="Parent directory for new repo (e.g. D:\\GIT\\FinishedMCPservers)")
    parser.add_argument("--github-user", default=None,  help="GitHub username — required if --create-repo")
    parser.add_argument("--create-repo", action="store_true", help="Create GitHub repo and push")
    args = parser.parse_args()

    n = names(args.slug)

    print(f"\nNew product: {n['repo']}")
    print(f"  NuGet:     {args.nuget} {args.version}")
    print(f"  Namespace: {n['server_ns']}")
    print(f"  Output:    {args.output_dir}")

    root = scaffold(n, args.nuget, args.version, args.output_dir)
    if not root:
        return

    github_repo = None
    if args.create_repo:
        if not args.github_user:
            print("\nERROR: --github-user required with --create-repo")
            return
        try:
            github_repo = git_init_and_push(root, n, args.github_user)
        except RuntimeError as e:
            print(f"\nERROR during git/GitHub: {e}")
            print("  Scaffold is on disk — push manually.")

    register_product(n, args.nuget, args.version, github_repo)

    print(f"\nDone! Next steps:")
    print(f"  1. Read docs/new-product-analysis-template.md")
    print(f"  2. Analyse {args.nuget} API and fill in {n['server_dir']}/Tools/{n['cap']}Tools.cs")
    print(f"  3. Update tool-map.md")
    print(f"  4. Write tests in {n['tests_dir']}/")
    print(f"  5. Run: dotnet build && dotnet test")
    if not args.create_repo:
        print(f"  6. Create GitHub repo and push manually")
        print(f"     gh repo create {n['repo']} --private")
        print(f"     git -C \"{root}\" init -b main && git -C \"{root}\" add -A")
        print(f"     git -C \"{root}\" commit -m 'feat: initial scaffold'")
        print(f"     git -C \"{root}\" remote add origin https://github.com/YOUR_USER/{n['repo']}.git")
        print(f"     git -C \"{root}\" push -u origin main")


if __name__ == "__main__":
    main()
