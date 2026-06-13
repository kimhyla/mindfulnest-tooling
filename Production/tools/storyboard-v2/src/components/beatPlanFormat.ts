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
export function beatPlanRowToLine(row: BeatPlanRow): string {
  const speaker = row.beat_type === 'stage_direction'
    ? '[Stage Direction]'
    : (row.speaker || 'Character').trim();
  const emotion = (row.emotion || 'neutral').trim();
  const dialogue = (row.dialogue_text || '').trim();
  const scene = (row.scene_notes || '').trim();
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

  const headerMatch = trimmed.match(/^(.+?)\s+\[([^\]]+)\]:\s*(.+)$/);
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
  const emotion = headerMatch[2].trim();
  let tail = headerMatch[3].trim();

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
  return {
    beat_index: beatIndex,
    beat_type: isStage ? 'stage_direction' : 'dialogue',
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
