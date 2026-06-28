import { describe, expect, it } from 'vitest';

import { lintKlingO3PromptContradictions } from '../promptContradictionLint';

const CONTRADICTORY =
  'Camera: stable. No flowers. Nothing additional is added.\n'
  + "Children's style, blooming Sweetroses in background.\n"
  + 'Sweetrose wreath visible behind her.';

const CLEAN =
  'Camera: stable. No flowers. Nothing additional is added.\n'
  + "Children's style, warm gold light.\n"
  + 'Glowing Rune-Stone visible behind her.';

describe('lintKlingO3PromptContradictions', () => {
  it('flags Event_3 Loral-style flower contradiction', () => {
    const warnings = lintKlingO3PromptContradictions(CONTRADICTORY);
    expect(warnings.length).toBeGreaterThan(0);
    expect(warnings.some((w) => w.includes('No flowers'))).toBe(true);
  });

  it('passes when negations have no conflicting positives', () => {
    expect(lintKlingO3PromptContradictions(CLEAN)).toEqual([]);
  });
});
