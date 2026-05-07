"""Tests for scripts/new_product.py — pure function tests, no filesystem/network."""
import pytest
from scripts.new_product import (
    names,
    t_server_csproj,
    t_program,
    t_licensing,
    t_tools_stub,
    t_tests_csproj,
    t_sln,
    t_gitignore,
    t_ci,
    MCP_VERSION,
    HOST_VERSION,
)


class TestNames:
    def test_basic_slug(self):
        n = names("words")
        assert n["slug"]      == "words"
        assert n["cap"]       == "Words"
        assert n["prefix"]    == "WordsMcp"
        assert n["repo"]      == "aspose-words-mcp"
        assert n["server_ns"] == "WordsMcp.Server"
        assert n["tests_ns"]  == "WordsMcp.Tests"
        assert n["solution"]  == "AsposeWordsMcp"

    def test_svg_slug(self):
        n = names("svg")
        assert n["prefix"]  == "SvgMcp"
        assert n["solution"] == "AsposeSvgMcp"
        assert n["repo"]    == "aspose-svg-mcp"

    def test_server_dir_format(self):
        n = names("font")
        assert n["server_dir"] == "src/FontMcp.Server"
        assert n["tests_dir"]  == "tests/FontMcp.Tests"

    def test_multichar_slug(self):
        n = names("imaging")
        assert n["prefix"] == "ImagingMcp"
        assert n["repo"]   == "aspose-imaging-mcp"


class TestServerCsproj:
    def setup_method(self):
        self.n = names("svg")
        self.content = t_server_csproj(self.n, "Aspose.SVG", "25.1.0")

    def test_contains_nuget_package(self):
        assert 'Include="Aspose.SVG"' in self.content

    def test_contains_version(self):
        assert 'Version="25.1.0"' in self.content

    def test_contains_mcp_sdk(self):
        assert "ModelContextProtocol" in self.content
        assert MCP_VERSION in self.content

    def test_contains_hosting(self):
        assert "Microsoft.Extensions.Hosting" in self.content
        assert HOST_VERSION in self.content

    def test_targets_net8(self):
        assert "net8.0" in self.content


class TestProgram:
    def setup_method(self):
        self.n = names("words")
        self.content = t_program(self.n, "Aspose.Words")

    def test_uses_correct_namespace(self):
        assert "WordsMcp.Server" in self.content

    def test_registers_tools_from_assembly(self):
        assert "WithToolsFromAssembly" in self.content

    def test_uses_stdio_transport(self):
        assert "WithStdioServerTransport" in self.content

    def test_applies_license(self):
        assert "Licensing.Apply" in self.content

    def test_logs_to_stderr(self):
        assert "LogToStandardErrorThreshold" in self.content


class TestLicensing:
    def setup_method(self):
        self.n = names("font")
        self.content = t_licensing(self.n, "Aspose.Font")

    def test_uses_env_var(self):
        assert "ASPOSE_LICENSE_PATH" in self.content

    def test_mentions_product_name(self):
        assert "Aspose.Font" in self.content

    def test_has_evaluation_fallback(self):
        assert "evaluation mode" in self.content

    def test_uses_stream_not_path(self):
        # Stream-based license loading is more reliable than path string
        assert "File.OpenRead" in self.content


class TestToolsStub:
    def test_contains_tool_type_attribute(self):
        n = names("svg")
        content = t_tools_stub(n, "Aspose.SVG")
        assert "[McpServerToolType]" in content

    def test_uses_correct_namespace(self):
        n = names("svg")
        content = t_tools_stub(n, "Aspose.SVG")
        assert "SvgMcp.Server.Tools" in content

    def test_contains_success_helper(self):
        n = names("svg")
        content = t_tools_stub(n, "Aspose.SVG")
        assert "Success" in content
        assert "success = true" in content

    def test_contains_error_helper(self):
        n = names("svg")
        content = t_tools_stub(n, "Aspose.SVG")
        assert "Error" in content
        assert "success = false" in content


class TestSolution:
    def test_contains_server_project(self):
        n = names("svg")
        sln = t_sln(n)
        assert "SvgMcp.Server" in sln

    def test_contains_tests_project(self):
        n = names("svg")
        sln = t_sln(n)
        assert "SvgMcp.Tests" in sln

    def test_unique_guids(self):
        n = names("svg")
        sln1 = t_sln(n)
        sln2 = t_sln(n)
        # Each call generates fresh GUIDs
        assert sln1 != sln2


class TestGitignore:
    def setup_method(self):
        self.content = t_gitignore()

    def test_ignores_bin(self):
        assert "bin/" in self.content

    def test_ignores_env(self):
        assert ".env" in self.content

    def test_ignores_license_files(self):
        assert "*.lic" in self.content

    def test_ignores_claude_settings(self):
        assert ".claude/" in self.content


class TestCi:
    def setup_method(self):
        self.n = names("svg")
        self.content = t_ci(self.n)

    def test_runs_on_main(self):
        assert '"main"' in self.content

    def test_has_build_step(self):
        assert "dotnet build" in self.content

    def test_has_test_step(self):
        assert "dotnet test" in self.content

    def test_targets_dotnet_8(self):
        assert "8.0.x" in self.content
