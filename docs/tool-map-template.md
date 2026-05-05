# Tool Map — Aspose.PUB MCP Server

Maps Aspose.PUB API methods to MCP tool names.

## API → Tool mapping

| Aspose.PUB API | MCP Tool | Notes |
|----------------|----------|-------|
| `PubFactory.CreateParser(stream)` → `parser.Parse()` | All tools | Core parsing step |
| `PubFactory.CreatePdfConverter().ConvertToPdf(doc, stream)` | `convert_pub_to_pdf` | Dedicated PDF converter |
| `PubFactory.CreatePubConverter().ConvertToFormat(doc, stream, format)` | `convert_pub_to_format` | All non-PDF formats |
| `document.SummaryInfo` + `document.DocumentSummaryInfo` | `get_pub_metadata` | Read-only metadata |
| Try/catch around `parser.Parse()` | `validate_pub_file` | Exception = invalid file |
| Static server info | `get_pub_capabilities` | No Aspose API call |

## Supported `PubExportFormats` values

| Format string (MCP input) | `PubExportFormats` enum | MIME type |
|--------------------------|------------------------|-----------|
| `jpg` / `jpeg` | `Jpg` | `image/jpeg` |
| `png` | `Png` | `image/png` |
| `tiff` | `Tiff` | `image/tiff` |
| `gif` | `Gif` | `image/gif` |
| `bmp` | `Bmp` | `image/bmp` |
| `doc` | `Doc` | `application/msword` |
| `docx` | `Docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| `xls` | `Xls` | `application/vnd.ms-excel` |
| `xlsx` | `Xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| `csv` | `Csv` | `text/csv` |
| `pptx` | `Pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` |
| `xps` | `Xps` | `application/vnd.ms-xpsdocument` |
| `epub` | `Epub` | `application/epub+zip` |
| `tex` | `Tex` | `application/x-tex` |
| `mhtml` | `Mhtml` | `multipart/related` |
| `html` | `Html` | `text/html` |
| `svg` | `Svg` | `image/svg+xml` |

## `SummaryInfo` properties

| Property | Type | Description |
|----------|------|-------------|
| `Title` | `string?` | Document title |
| `Author` | `string?` | Document author |
| `Subject` | `string?` | Document subject |
| `Keywords` | `string?` | Document keywords |
| `Comments` | `string?` | Comments |
| `LastAuthor` | `string?` | Last saved by |
| `Template` | `string?` | Template name |
| `RevNumber` | `string?` | Revision number |
| `AppName` | `string?` | Application name |
| `PageCount` | `int` | Number of pages |
| `WordCount` | `int` | Word count |
| `CharCount` | `int` | Character count |
| `DocSecurity` | `int` | Document security flags |

## `DocSummaryInfo` properties

| Property | Type | Description |
|----------|------|-------------|
| `Category` | `string?` | Document category |
| `Company` | `string?` | Company name |
| `Language` | `string?` | Document language |

## Known limitations

- **No .pub creation**: `PubFactory` has no method to create a .pub document from scratch.
- **No save-back to .pub**: After parsing and modifying metadata in memory, there is no API to serialize the `Document` back to .pub format. This is why `set_pub_metadata` is not implemented.
- **Evaluation watermarks**: Without a valid Aspose.PUB license, all output files contain a watermark.
- **Aspose.PDF runtime dependency**: Aspose.PUB 25.x uses `Aspose.PDF` internally as a rendering engine for **all** format conversions — not just PDF output. This dependency is not declared in the Aspose.PUB NuGet manifest (nuspec) but is required at runtime. `Aspose.PDF 25.12.0` is therefore included as an explicit package reference. A separate Aspose.PDF license is needed to remove the additional Aspose.PDF evaluation watermark from converted files.
