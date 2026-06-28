/** Mirror server lint_kling_o3_prompt_contradictions — block Generate before submit. */

const FLOWER_POSITIVE_RE =
  /\b(?:sweet\s*[- ]?roses?|sweetroses?|blooming(?:\s+\w+){0,3}\s+(?:in\s+)?background|rose\s+wreath|sweetrose\s+wreath|flowers?\s+in\s+(?:the\s+)?background|full\s+garden\s+of\s+sweet)\b/i;

const ADDITION_POSITIVE_RE =
  /\b(?:blooming|(?:sweet\s*[- ]?)?rose\s+wreath|wreath|sprouts?|blooms?\s+(?:in|around|on))\b/i;

export function lintKlingO3PromptContradictions(prompt: string): string[] {
  const text = (prompt ?? '').trim();
  if (!text) return [];
  const lower = text.toLowerCase();
  const warnings: string[] = [];

  const noFlowers = /\bno flowers\b/i.test(lower);
  const flowerPositive = FLOWER_POSITIVE_RE.test(text);
  if (noFlowers && flowerPositive) {
    warnings.push(
      'Prompt says "No flowers" but also describes Sweetroses/flowers/blooming — '
      + 'Kling follows positive visuals. Remove all flower lines from style and scene notes.',
    );
  }

  const noAdditions = /\bnothing additional is added\b/i.test(lower);
  if (noAdditions && (flowerPositive || ADDITION_POSITIVE_RE.test(text))) {
    warnings.push(
      'Prompt says "Nothing additional is added" but also describes blooming additions — '
      + 'remove conflicting style/scene-notes lines.',
    );
  }

  return warnings;
}
