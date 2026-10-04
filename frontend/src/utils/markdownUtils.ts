/**
 * Remove common markdown formatting from a string.
 * Strips heading markers (#), bold (**), italic (*), underline bold (__),
 * underline italic (_), and inline code backticks (`).
 */
export function cleanMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s*/, '')  // Remove leading hashes
    .replace(/\*\*/g, '')       // Remove bold markers
    .replace(/\*/g, '')         // Remove italic markers
    .replace(/__/g, '')         // Remove underline bold
    .replace(/_/g, '')          // Remove underline italic
    .replace(/`/g, '')          // Remove code markers
    .trim();
}
