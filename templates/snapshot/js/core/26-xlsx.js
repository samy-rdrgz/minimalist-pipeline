/* ---------- A spreadsheet file (.xlsx), written in the page ----------
   No library (the page works offline): the few XML parts a spreadsheet needs, in a zip
   stored without compression. sheets: [{name, cols: [width in characters],
   rows: [[cell]]}], the first row the header (bold, kept in view). A cell: a string,
   a number, null (empty), or {v: 0..1, pct: true} shown as a percentage. */
const XLSX = (() => {
  const CRC = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c >>> 0;
    }
    return t;
  })();
  const crc32 = bytes => {
    let c = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) c = CRC[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  /* files: [[path, text]] → the zip's bytes (method 0: stored). */
  function zip(files) {
    const enc = new TextEncoder(),
      parts = [],
      dir = [];
    let at = 0;
    const u16 = n => [n & 0xff, (n >>> 8) & 0xff],
      u32 = n => [n & 0xff, (n >>> 8) & 0xff, (n >>> 16) & 0xff, (n >>> 24) & 0xff];
    files.forEach(([path, text]) => {
      const name = enc.encode(path),
        data = enc.encode(text),
        crc = crc32(data);
      const common = [
        ...u16(20),
        ...u16(0x0800),
        ...u16(0),
        ...u16(0),
        ...u16(0x21),
        ...u32(crc),
        ...u32(data.length),
        ...u32(data.length),
        ...u16(name.length),
        ...u16(0)
      ];
      const head = new Uint8Array([...u32(0x04034b50), ...common]);
      parts.push(head, name, data);
      dir.push(
        new Uint8Array([
          ...u32(0x02014b50),
          ...u16(20),
          ...common,
          ...u16(0),
          ...u16(0),
          ...u16(0),
          ...u32(0),
          ...u32(at)
        ]),
        name
      );
      at += head.length + name.length + data.length;
    });
    const size = dir.reduce((s, p) => s + p.length, 0);
    const end = new Uint8Array([
      ...u32(0x06054b50),
      ...u16(0),
      ...u16(0),
      ...u16(files.length),
      ...u16(files.length),
      ...u32(size),
      ...u32(at),
      ...u16(0)
    ]);
    return new Blob([...parts, ...dir, end], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    });
  }
  const x = s =>
    String(s)
      .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  const col = n => {
    let s = '';
    for (n++; n; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(65 + ((n - 1) % 26)) + s;
    return s;
  };
  function sheetXML(sh) {
    const rows = sh.rows
      .map(
        (r, i) =>
          `<row r="${i + 1}">${r
            .map((c, j) => {
              const ref = col(j) + (i + 1),
                st = i === 0 ? ' s="1"' : '';
              if (c == null || c === '') return '';
              if (typeof c === 'number') return `<c r="${ref}"${st}><v>${c}</v></c>`;
              if (typeof c === 'object' && c.pct) return `<c r="${ref}" s="2"><v>${c.v}</v></c>`;
              return `<c r="${ref}" t="inlineStr"${st}><is><t xml:space="preserve">${x(c)}</t></is></c>`;
            })
            .join('')}</row>`
      )
      .join('');
    const cols = (sh.cols || [])
      .map((w, j) => `<col min="${j + 1}" max="${j + 1}" width="${w}" customWidth="1"/>`)
      .join('');
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>${cols ? `<cols>${cols}</cols>` : ''}<sheetData>${rows}</sheetData>${sh.rows.length > 1 ? `<autoFilter ref="A1:${col(Math.max(0, sh.rows[0].length - 1))}${sh.rows.length}"/>` : ''}</worksheet>`;
  }
  /* The workbook's bytes, as a Blob. */
  function book(sheets) {
    const names = sheets.map((s, i) =>
      x(s.name.replace(/[\\/?*[\]:]/g, ' ').slice(0, 31) || 'Sheet' + (i + 1))
    );
    return zip([
      [
        '[Content_Types].xml',
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>${sheets.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join('')}</Types>`
      ],
      [
        '_rels/.rels',
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`
      ],
      [
        'xl/workbook.xml',
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>${names.map((n, i) => `<sheet name="${n}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join('')}</sheets></workbook>`
      ],
      [
        'xl/_rels/workbook.xml.rels',
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${sheets.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join('')}<Relationship Id="rId${sheets.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`
      ],
      [
        'xl/styles.xml',
        `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="9" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`
      ],
      ...sheets.map((s, i) => [`xl/worksheets/sheet${i + 1}.xml`, sheetXML(s)])
    ]);
  }
  return { book };
})();
/* A Blob saved under name: a link clicked. */
function saveBlob(blob, name) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(a.href);
    a.remove();
  }, 1000);
}
