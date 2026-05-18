// Static parenthetical-suggestion library — V59 Phase 6 D2 (per spec line 92).
// Sourced from Production/docs/BEAT_PARENTHETICAL_CONVENTION_v1.md.
// Path α (FREE): no LLM call; static menu inserted at cursor.

export interface ParentheticalSuggestion {
  emotion: string;       // short label for the dropdown
  text: string;          // the parenthetical to insert (no surrounding parens)
  species: "bird" | "mammal" | "any";
}

export const PARENTHETICAL_SUGGESTIONS: ParentheticalSuggestion[] = [
  { emotion: "shock", species: "bird",   text: "wide bright shocked eyes, raised brow ridges, beak at rest" },
  { emotion: "shock", species: "mammal", text: "wide shocked eyes, ears flared back, mouth at rest" },
  { emotion: "joy",   species: "bird",   text: "bright cheerful eyes, soft wing settle, beak at rest" },
  { emotion: "joy",   species: "mammal", text: "warm bright eyes, slight smile, mouth at rest, ears forward" },
  { emotion: "calm",  species: "bird",   text: "soft relaxed eyes, settled wings, beak at rest" },
  { emotion: "calm",  species: "mammal", text: "soft relaxed eyes, settled posture, mouth at rest" },
  { emotion: "determination", species: "bird",   text: "focused steady eyes, wings folded, beak at rest" },
  { emotion: "determination", species: "mammal", text: "focused steady eyes, set jaw, mouth at rest" },
  { emotion: "curiosity", species: "any", text: "tilted head, curious bright eyes, beak/mouth at rest" },
  { emotion: "fear",       species: "any", text: "shrunken posture, wide worried eyes, beak/mouth at rest" },
  { emotion: "wonder",     species: "any", text: "soft awe-filled eyes, wings/paws drawn close, beak/mouth at rest" },
  { emotion: "courage",    species: "any", text: "lifted brow, steady determined eyes, posture upright, beak/mouth at rest" },
  { emotion: "sadness",    species: "any", text: "downcast eyes, drooped posture, beak/mouth at rest" },
  { emotion: "relief",     species: "any", text: "softened tension, eyes half-closed in relief, beak/mouth at rest" },
  { emotion: "doubt",      species: "any", text: "narrowed thoughtful eyes, slight head tilt, beak/mouth at rest" },
];
