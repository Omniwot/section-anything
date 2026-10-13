/** Distinct hue per section: golden-angle spacing keeps neighbours apart. */
export function sectionColor(id: number): string {
  return `hsl(${Math.round((id * 137.508) % 360)} 72% 52%)`;
}
