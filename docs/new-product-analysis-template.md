# Kako napraviti MCP analizu za bilo koji Aspose produkt

## Proces u 3 koraka

### Korak 1: Prikupi informacije o produktu

Otvori ove URL-ove (zamijeni `<product>` s imenom produkta, npr. `zip`, `imaging`, `font`):

| Izvor | URL |
|-------|-----|
| Developer Guide | `https://docs.aspose.com/<product>/net/developer-guide/` |
| API Reference | `https://reference.aspose.com/<product>/net/` |
| Features | `https://docs.aspose.com/<product>/net/features/` |
| GitHub primjeri | `https://github.com/aspose-<product>/Aspose.<Product>-for-.NET` |
| NuGet | `https://www.nuget.org/packages/Aspose.<Product>` |
| Product page | `https://products.aspose.com/<product>/net/` |

### Korak 2: Pitaj Claude (ovdje ili u Claude Code) sljedeći prompt

```
Analiziraj Aspose.<PRODUCT> za .NET i napravi MCP analizu.

Dokumentacija:
- Developer Guide: https://docs.aspose.com/<product>/net/developer-guide/
- API Reference: https://reference.aspose.com/<product>/net/
- GitHub: https://github.com/aspose-<product>/Aspose.<Product>-for-.NET

Trebam:

1. ŠTO PRODUKT MOŽE — sve operacije iz Developer Guide-a, grupirane po kategorijama
2. KLJUČNE KLASE — factory klase, interface-i, enumi, DTO-ovi
3. PODRŽANI FORMATI — input i output formati
4. OGRANIČENJA — što API NE može (npr. jednosmjerna konverzija, nema kreiranja od nule)
5. TOOL MAPA — mapiranje svake mogućnosti na MCP tool:
   - Naziv toola (format: aspose.<product>.<domain>.<action> ili kraći ako je mali API)
   - Input (base64/filePath/parametri)
   - Output (base64/JSON)
6. PROMPT ZA CLAUDE CODE TERMINAL — kompletan prompt koji mogu zalijepiti u `claude` sesiju da generira MCP server
7. KORAK-PO-KORAK ALTERNATIVA — za inkrementalni pristup

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
- GitHub: https://github.com/aspose-zip/Aspose.ZIP-for-.NET

Trebam:

1. ŠTO PRODUKT MOŽE — sve operacije iz Developer Guide-a
2. KLJUČNE KLASE — factory klase, interface-i, enumi
3. PODRŽANI FORMATI — input i output formati
4. OGRANIČENJA — što NE može
5. TOOL MAPA — MCP toolovi
6. PROMPT ZA CLAUDE CODE TERMINAL
7. KORAK-PO-KORAK ALTERNATIVA

Spremi kao aspose-zip-mcp-analysis.md
```

---

## Checklist za svaki produkt

Prije nego kreneš generirat MCP server, provjeri:

- [ ] Developer Guide postoji i ima sadržaj (neki produkti imaju prazne stranice)
- [ ] API Reference ima klase navedene u sidebar-u
- [ ] GitHub repo ima Examples folder s kodom
- [ ] NuGet paket podržava net8.0 (ili barem .NET Standard 2.1)
- [ ] Znaš ograničenja (jednosmjerna konverzija? read-only? evaluacija bez licence?)
