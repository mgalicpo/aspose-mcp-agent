# Upute: Publish MCP servera na GitHub

GitHub username: `mgalicpo`
Lokacija: `D:\GIT\FinishedMCPservers\`

---

## 1. aspose-pub-mcp (GitHub repo već kreiran)

```powershell
cd D:\GIT\FinishedMCPservers\aspose-pub-mcp

git commit -m "Initial commit: Aspose.PUB MCP server"
git remote add origin https://github.com/mgalicpo/aspose-pub-mcp.git
git push -u origin main
```

---

## 2. aspose-font-mcp

```powershell
cd D:\GIT\FinishedMCPservers\aspose-font-mcp

git commit -m "Initial commit: Aspose.Font MCP server"
gh repo create aspose-font-mcp --public --description "MCP server for Aspose.Font .NET"
git remote add origin https://github.com/mgalicpo/aspose-font-mcp.git
git push -u origin main
```

---

## 3. aspose-note-mcp

```powershell
cd D:\GIT\FinishedMCPservers\aspose-note-mcp

git commit -m "Initial commit: Aspose.Note MCP server"
gh repo create aspose-note-mcp --public --description "MCP server for Aspose.Note .NET"
git remote add origin https://github.com/mgalicpo/aspose-note-mcp.git
git push -u origin main
```

---

## 4. aspose-zip-mcp

```powershell
cd D:\GIT\FinishedMCPservers\aspose-zip-mcp

git commit -m "Initial commit: Aspose.ZIP MCP server"
gh repo create aspose-zip-mcp --public --description "MCP server for Aspose.ZIP .NET"
git remote add origin https://github.com/mgalicpo/aspose-zip-mcp.git
git push -u origin main
```

---

## 5. mcp-agent (centralni tracker)

```powershell
cd D:\GIT\mcp-agent

git commit -m "Initial commit: Aspose MCP version tracker"
gh repo create aspose-mcp-agent --public --description "Central tracker for Aspose MCP server versions"
git remote add origin https://github.com/mgalicpo/aspose-mcp-agent.git
git push -u origin main
```

---

## 6. Dodaj label u aspose-mcp-agent (potrebno za workflow)

```powershell
cd D:\GIT\mcp-agent
gh label create "aspose-update" --color "0075ca" --description "Aspose NuGet version update"
```

---

## 7. Testiraj version tracker workflow

```powershell
cd D:\GIT\mcp-agent
gh workflow run check-versions.yml
```

Provjeri rezultat:
```powershell
gh run list --workflow=check-versions.yml
gh run view   # zadnji run
```

Ili idi na: https://github.com/mgalicpo/aspose-mcp-agent/actions

---

## Redoslijed

1. aspose-pub-mcp (repo vec postoji)
2. aspose-font-mcp
3. aspose-note-mcp
4. aspose-zip-mcp
5. aspose-mcp-agent
6. Dodaj label
7. Pokreni workflow i provjeri da kreira Issue
