import { useEffect, useState } from 'preact/hooks';
import { Modal } from './ui/Modal';
import { Spinner } from './ui/Spinner';

export interface BeatPlanRow {
  beat_index: number;
  beat_type: 'dialogue' | 'stage_direction';
  speaker: string;
  dialogue_text: string;
  emotion: string;
  scene_notes: string;
  skeleton_quote?: string;
  invented?: boolean;
}

export interface BeatPlanModalProps {
  open: boolean;
  storySummary: string;
  beatsPlan: BeatPlanRow[];
  approveStatus: 'idle' | 'sending';
  onClose: () => void;
  onApprove: (storySummary: string, beatsPlan: BeatPlanRow[]) => void;
}

export function BeatPlanModal({
  open,
  storySummary: initialSummary,
  beatsPlan: initialPlan,
  approveStatus,
  onClose,
  onApprove,
}: BeatPlanModalProps) {
  const [storySummary, setStorySummary] = useState(initialSummary);
  const [beatsPlan, setBeatsPlan] = useState<BeatPlanRow[]>(initialPlan);

  useEffect(() => {
    if (open) {
      setStorySummary(initialSummary);
      setBeatsPlan(initialPlan);
    }
  }, [open, initialSummary, initialPlan]);

  const updateRow = (index: number, patch: Partial<BeatPlanRow>) => {
    setBeatsPlan((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  };

  const removeRow = (index: number) => {
    setBeatsPlan((rows) => rows.filter((_, i) => i !== index).map((r, i) => ({ ...r, beat_index: i + 1 })));
  };

  const addRow = () => {
    setBeatsPlan((rows) => [
      ...rows,
      {
        beat_index: rows.length + 1,
        beat_type: 'dialogue',
        speaker: 'Character',
        dialogue_text: '',
        emotion: 'neutral',
        scene_notes: '',
        invented: false,
      },
    ]);
  };

  return (
    <Modal
      id="beat-plan"
      title="Review beat plan (edit before Approve)"
      panelClass="mn-modal-wide"
      open={open}
      onClose={onClose}
      footer={(
        <>
          <button type="button" class="mn-btn" data-testid="beat-plan-cancel" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            class="mn-btn mn-btn-primary"
            data-testid="beat-plan-approve"
            disabled={approveStatus === 'sending' || beatsPlan.length === 0}
            onClick={() => onApprove(storySummary, beatsPlan)}
          >
            {approveStatus === 'sending' ? (
              <><Spinner size="sm" inline /> Building Kling prompts…</>
            ) : 'Approve & populate beats'}
          </button>
        </>
      )}
    >
      <p class="mn-dim">
        Claude read the skeleton section for this video only. Edit the summary and script,
        then Approve to generate rich Kling O3 prompts.
      </p>
      <label class="mn-label" for="beat-plan-summary">Story summary</label>
      <textarea
        id="beat-plan-summary"
        class="mn-textarea"
        data-testid="beat-plan-summary"
        rows={5}
        value={storySummary}
        onInput={(e) => setStorySummary((e.target as HTMLTextAreaElement).value)}
      />
      <div class="mn-beat-plan-table" data-testid="beat-plan-rows">
        {beatsPlan.map((row, i) => (
          <div class="mn-beat-plan-row" key={`plan-${row.beat_index}-${i}`} data-testid={`beat-plan-row-${i}`}>
            <div class="mn-beat-plan-row-head">
              <strong>Beat {row.beat_index}</strong>
              <select
                value={row.beat_type}
                onChange={(e) => updateRow(i, {
                  beat_type: (e.target as HTMLSelectElement).value as BeatPlanRow['beat_type'],
                })}
              >
                <option value="dialogue">dialogue</option>
                <option value="stage_direction">stage_direction</option>
              </select>
              <button type="button" class="mn-btn mn-btn-sm" onClick={() => removeRow(i)}>Remove</button>
            </div>
            <input
              class="mn-input"
              placeholder="Speaker"
              value={row.speaker}
              onInput={(e) => updateRow(i, { speaker: (e.target as HTMLInputElement).value })}
            />
            <textarea
              class="mn-textarea"
              placeholder="Dialogue / stage text"
              rows={2}
              value={row.dialogue_text}
              onInput={(e) => updateRow(i, { dialogue_text: (e.target as HTMLTextAreaElement).value })}
            />
            <input
              class="mn-input"
              placeholder="Emotion / delivery"
              value={row.emotion}
              onInput={(e) => updateRow(i, { emotion: (e.target as HTMLInputElement).value })}
            />
            <textarea
              class="mn-textarea"
              placeholder="Scene notes (staging for Kling)"
              rows={2}
              value={row.scene_notes}
              onInput={(e) => updateRow(i, { scene_notes: (e.target as HTMLTextAreaElement).value })}
            />
          </div>
        ))}
      </div>
      <button type="button" class="mn-btn" data-testid="beat-plan-add-row" onClick={addRow}>
        + Add beat row
      </button>
    </Modal>
  );
}
