/** Browser magenta key — mirrors ffmpeg `chromakey=0xFF00FF:0.25:0.0` (wc_v13 encode matte). */
export function applyMagentaChromakey(imageData: ImageData): void {
  const d = imageData.data;
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i];
    const g = d[i + 1];
    const b = d[i + 2];
    const dr = Math.abs(r - 255) / 255;
    const dg = g / 255;
    const db = Math.abs(b - 255) / 255;
    const dist = Math.sqrt(dr * dr + dg * dg + db * db);
    if (dist < 0.28) {
      d[i + 3] = 0;
    }
  }
}
