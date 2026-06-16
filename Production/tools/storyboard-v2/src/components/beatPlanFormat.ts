import type { BeatPlanRow } from './BeatPlanModal';

/**
 * One line per beat for Kim's script-style edit box.
 *
 * Format:
 *   Speaker [emotion/delivery]: dialogue or action [staging / camera notes]
 *   [Stage Direction] [emotion]: action-only beat [optional staging]
 *
 * Brackets match how delivery + staging read in Kling prompts.
 */
const STILL_INSERT_HINT_RE = /\b(still insert|gpt still|inscription|runestone|carved text|pre-?made still)\b/i;

const PLAN_IMAGE_HEADER_RE = /^@Image1\s*\([^)]+\)\s*[.;,]?\s*(?:Scene from @Image2\s*[.;,]?\s*)?/i;
const PLAN_VOICE_LINE_RE = /\bVoice line:\s*.+?(?:"[^"]*"|'[^']*')\s*\.?\s*/gis;
const PLAN_STORYBOOK_TAIL_RE = /\s*Children's illustrated fantasy storybook style\.?\s*$/i;

/** Modal edit box: staging only — strip Kling prompt boilerplate Claude sometimes packs in scene_notes. */
function stripPlanSceneNotesForDisplay(sceneNotes: string): string {
  let notes = (sceneNotes || '').trim();
  if (!notes) return '';
  notes = notes.replace(PLAN_IMAGE_HEADER_RE, '').trim();
  notes = notes.replace(PLAN_VOICE_LINE_RE, '').trim();
  notes = notes.replace(PLAN_STORYBOOK_TAIL_RE, '').trim();
  if (notes.includes(';')) {
    const kept = notes.split(';')
      .map((part) => part.trim())
      .filter((part) => {
        const lower = part.toLowerCase();
        return !lower.startsWith('voice line:')
          && !lower.startsWith('@image1')
          && !lower.startsWith('scene from @image2');
      });
    if (kept.length > 0) {
      notes = kept.join('. ');
    }
  }
  return notes.replace(/\s+/g, ' ').trim();
}

/** Strip outer brackets so we never emit ``[[emotion]]`` in plan lines. */
function formatEmotionForLine(emotion: string): string {
  const e = (emotion || 'neutral').trim();
  if (e.startsWith('[') && e.endsWith(']')) {
    return e.slice(1, -1).trim();
  }
  return e;
}

export function beatPlanRowToLine(row: BeatPlanRow): string {
  const speaker = (row.beat_type === 'stage_direction' || row.beat_type === 'stage_still')
    ? '[Stage Direction]'
    : (row.speaker || 'Character').trim();
  const emotion = formatEmotionForLine(row.emotion || 'neutral');
  const dialogue = (row.dialogue_text || '').trim();
  const scene = stripPlanSceneNotesForDisplay(row.scene_notes || '');
  let line = `${speaker} [${emotion}]: ${dialogue}`;
  if (scene) {
    line += ` [${scene}]`;
  }
  return line;
}

export function beatPlanRowsToText(rows: BeatPlanRow[]): string {
  return rows.map(beatPlanRowToLine).join('\n\n');
}

/** Count beats separated by blank lines (paragraph breaks). */
export function countBeatPlanBlocks(text: string): number {
  return text.split(/\n\s*\n+/).map((b) => b.trim()).filter(Boolean).length;
}

/** Last `[...]` on the line is staging; earlier `[...]` after speaker is emotion. */
function parseBeatPlanLine(line: string, beatIndex: number): BeatPlanRow {
  const trimmed = line.trim();
  const invented = trimmed.includes('[CLAUDE INVENTED]');

  const headerMatch = trimmed.match(
    /^(.+?)\s+(?:\[\[([^\]]+)\]\]|\[([^\]]+)\]):\s*(.+)$/,
  );
  if (!headerMatch) {
    return {
      beat_index: beatIndex,
      beat_type: 'dialogue',
      speaker: 'Character',
      dialogue_text: trimmed,
      emotion: 'neutral',
      scene_notes: '',
      invented,
    };
  }

  const speakerRaw = headerMatch[1].trim();
  const emotion = (headerMatch[2] || headerMatch[3] || 'neutral').trim();
  let tail = headerMatch[4].trim();

  let scene_notes = '';
  const sceneMatch = tail.match(/\s+\[([^\]]+)\]\s*$/);
  if (sceneMatch && sceneMatch.index !== undefined) {
    scene_notes = sceneMatch[1].trim();
    tail = tail.slice(0, sceneMatch.index).trim();
  }

  let dialogue_text = tail;
  if (
    (dialogue_text.startsWith('"') && dialogue_text.endsWith('"'))
    || (dialogue_text.startsWith("'") && dialogue_text.endsWith("'"))
  ) {
    dialogue_text = dialogue_text.slice(1, -1);
  }

  const isStage = /^(\[Stage Direction\]|Stage Direction)$/i.test(speakerRaw);
  const combined = `${tail} ${scene_notes}`;
  const isStill = STILL_INSERT_HINT_RE.test(combined) || STILL_INSERT_HINT_RE.test(trimmed);
  return {
    beat_index: beatIndex,
    beat_type: isStill ? 'stage_still' : (isStage ? 'stage_direction' : 'dialogue'),
    speaker: isStage ? '[Stage Direction]' : speakerRaw,
    dialogue_text,
    emotion: emotion || 'neutral',
    scene_notes,
    invented,
  };
}

export function parseBeatPlanText(text: string): BeatPlanRow[] {
  const blocks = text.split(/\n\s*\n+/).map((b) => b.trim()).filter(Boolean);
  return blocks.map((block, i) => {
    // Soft line wraps inside one beat → single logical line.
    const line = block.replace(/\s*\n\s*/g, ' ').trim();
    const row = parseBeatPlanLine(line, i + 1);
    row.beat_index = i + 1;
    return row;
  });
}
