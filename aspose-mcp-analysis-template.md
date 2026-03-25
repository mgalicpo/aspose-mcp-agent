# Kako napraviti MCP analizu za bilo koji Aspose produkt

## Proces u 3 koraka

### Korak 1: Prikupi informacije o produktu

Otvori ove URL-ove (zamijeni `<product>` s imenom produkta, npr. `zip`, `imaging`, `font`):

| Izvor | URL |
|-------|-----|
| Developer Guide | `https://docs.aspose.com/<product>/net/developer-guide/` |
| API Reference | `https://reference.aspose.com/<product>/net/` |
| Features | `https://docs.aspose.com/<product>/net/features/` |
| Release Notes | `https://releases.aspose.com/<product>/net/` |
| GitHub primjeri | `https://github.com/aspose-<product>/Aspose.<Product>-for-.NET` |
| NuGet | `https://www.nuget.org/packages/Aspose.<Product>` |
| Product page | `https://products.aspose.com/<product>/net/` |

### Korak 2: Pitaj Claude (ovdje ili u Claude Code) sljedeći prompt

```
Analiziraj Aspose.<PRODUCT> za .NET i napravi MCP analizu.

Dokumentacija:
- Developer Guide: https://docs.aspose.com/<product>/net/developer-guide/
- API Reference: https://reference.aspose.com/<product>/net/
- Release Notes: https://releases.aspose.com/<product>/net/
- GitHub: https://github.com/aspose-<product>/Aspose.<Product>-for-.NET

Trebam:

1. ŠTO PRODUKT MOŽE — sve operacije iz Developer Guide-a, grupirane po kategorijama

2. KLJUČNE KLASE — factory klase, interface-i, enumi, DTO-ovi

3. PODRŽANI FORMATI — input i output formati

4. OGRANIČENJA — što API NE može (npr. jednosmjerna konverzija, nema kreiranja od nule)

5. TOOL MAPA — mapiranje svake mogućnosti na MCP tool:
   - Naziv toola (format: aspose.<product>.<domain>.<action>)
   - Behavior annotation: ReadOnly | Destructive | Idempotent | OpenWorld
   - Input (base64/filePath/parametri + JSON Schema tipovi)
   - Output (base64/JSON)
   - Napomena o sigurnosti ako tool prima path ili user input

6. SESSION ANALYSIS — treba li ovaj produkt session management?
   - Stateful formati (Word, Excel, PDF): open → edit → save/close pattern
   - Stateless formati (Font, ZIP, PUB): svaki tool je self-contained
   - Zaključak: da/ne + obrazloženje

7. SECURITY REQUIREMENTS — specifično za ovaj produkt:
   - Koji inputi trebaju path validation (sprečava directory traversal)?
   - Koji outputi trebaju sanitizaciju (ukloni stacktrace, putanje, licence data)?
   - Koji string inputi trebaju max-length ograničenje?

8. DISTRIBUTION STRATEGY — kako će korisnici pokretati server?
   - `dotnet run` (dev-friendly, nema build)
   - Compiled binary (GitHub Releases, za non-.NET korisnike)
   - `dotnet tool install` (ako se planira NuGet distribucija)
   - Preporučeni pristup za ovaj produkt

9. PROMPT ZA CLAUDE CODE TERMINAL — kompletan prompt koji mogu zalijepiti u `claude`
   sesiju da generira MCP server. Prompt MORA uključivati:
   - Repo strukturu (src/, tests/, fixtures/)
   - Tool implementaciju s behavior annotations
   - Session management (ako je relevantno)
   - SecurityHelper za path validation
   - CI workflow (.github/workflows/ci.yml)
   - Dependabot config (.github/dependabot.yml) za auto NuGet updates
   - README s install/run/tools/client-config sekcijama

10. KORAK-PO-KORAK ALTERNATIVA — za inkrementalni pristup

Spremi rezultat kao aspose-<product>-mcp-analysis.md
```

### Korak 3: Generiraj MCP server

Koristi generirani prompt iz analize u Claude Code terminalu:

```powershell
mkdir D:\GIT\aspose-<product>-mcp
cd D:\GIT\aspose-<product>-mcp
claude
# zalijepi prompt iz analysis dokumenta
```

---

## Primjer: kako bi izgledao Korak 2 za Aspose.ZIP

```
Analiziraj Aspose.ZIP za .NET i napravi MCP analizu.

Dokumentacija:
- Developer Guide: https://docs.aspose.com/zip/net/developer-guide/
- API Reference: https://reference.aspose.com/zip/net/
- Release Notes: https://releases.aspose.com/zip/net/
- GitHub: https://github.com/aspose-zip/Aspose.ZIP-for-.NET

Trebam sve sekcije: ŠTO MOŽE, KLJUČNE KLASE, FORMATI, OGRANIČENJA,
TOOL MAPA (s annotations), SESSION ANALYSIS, SECURITY, DISTRIBUTION,
PROMPT ZA CLAUDE CODE TERMINAL, KORAK-PO-KORAK.

Spremi kao aspose-zip-mcp-analysis.md
```

---

## Checklist za svaki produkt

Prije nego kreneš generirat MCP server, provjeri:

**Sadržaj**
- [ ] Developer Guide postoji i ima sadržaj (neki produkti imaju prazne stranice)
- [ ] API Reference ima klase navedene u sidebar-u
- [ ] GitHub repo ima Examples folder s kodom
- [ ] NuGet paket podržava net8.0 (ili barem .NET Standard 2.1)
- [ ] Znaš ograničenja (jednosmjerna konverzija? read-only? evaluacija bez licence?)

**Implementacija**
- [ ] Svaki tool ima behavior annotation (ReadOnly/Destructive/Idempotent/OpenWorld)
- [ ] Path inputi imaju SecurityHelper validation (directory traversal prevention)
- [ ] Error output ne sadrži file paths ni stack traces
- [ ] Server radi u evaluation mode (bez licence, s watermark ograničenjima)

**CI/CD**
- [ ] `.github/workflows/ci.yml` — build + test na push/PR
- [ ] `.github/dependabot.yml` — weekly NuGet check za auto-bump PR-ove
- [ ] GitHub Release workflow — publish binary na tag push

**README**
- [ ] Install instrukcije (prerequisites + komande)
- [ ] Popis toolova s opisima
- [ ] Primjer JSON tool call-a za svaki tool
- [ ] Claude Desktop config JSON
- [ ] Claude Code CLI komanda (`claude mcp add ...`)
- [ ] Aspose licence napomena

---

## Behavior Annotations (MCP SDK 0.6.0+)

Svaki tool u MCP serveru treba biti označen. Referenca:

| Annotation | Kada koristiti | Primjer |
|---|---|---|
| `ReadOnly` | Tool ne mijenja podatke | `convert`, `extract`, `get_info` |
| `Destructive` | Briše ili mijenja originalne podatke | `delete_entry`, `overwrite` |
| `Idempotent` | Višestruki pozivi = isti rezultat | `set_password`, `add_entry` (bez duplikata) |
| `OpenWorld` | Output može sadržavati podatke izvan inputa | `recognize`, `ocr`, `detect` |

---

## Versioning: Dependabot config template

Dodaj u svaki generirani MCP server repo:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: nuget
    directory: /src
    schedule:
      interval: weekly
    commit-message:
      prefix: "chore: bump"
    labels: ["aspose-update", "automated"]
```

Ovo automatski kreira PR kad Aspose izda novu NuGet verziju.
Ako CI prođe → safe to merge (patch/minor). Ako ne prođe → ručni review.

---

## Referentna implementacija

Za inspiraciju pogledaj: **[xjustloveux/aspose-mcp-server](https://github.com/xjustloveux/aspose-mcp-server)**
- 115 toolova za Aspose.Total (Word, Excel, Slides, PDF, OCR, Email, BarCode)
- STDIO + HTTP + WebSocket transport
- Session management za stateful dokumente
- SecurityHelper s path validation i input sanitizacijom
- Behavior annotations, config.json, GitHub Pages dokumentacija
- Multi-platform CI (Windows/Linux/macOS)

Ova implementacija pokriva uredske formate (Word, Excel, PDF). Tvoji MCP serveri
(PUB, Note, Font, ZIP) pokrivaju drugačije domene — nema duplikacije.
