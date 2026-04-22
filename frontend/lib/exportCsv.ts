export function downloadCsv(filename: string, rows: Record<string, unknown>[], columns?: string[]) {
  if (rows.length === 0) return;
  const keys = columns ?? Object.keys(rows[0]);
  const header = keys.join(',');

  function formatCellValue(value: unknown): string {
    if (Array.isArray(value)) {
      return value.map(item => String(item)).join(' | ');
    }
    if (value instanceof Date) {
      return value.toISOString();
    }
    return String(value ?? '');
  }

  const body = rows.map(row =>
    keys.map(k => {
      const s = formatCellValue(row[k]);
      return s.includes(',') || s.includes('"') || s.includes('\n')
        ? `"${s.replace(/"/g, '""')}"`
        : s;
    }).join(',')
  ).join('\n');
  const blob = new Blob([`${header}\n${body}`], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
