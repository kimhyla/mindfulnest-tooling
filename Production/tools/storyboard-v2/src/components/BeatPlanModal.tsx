import { useEffect, useState } from 'preact/hooks';
import { Modal } from './ui/Modal';
import { Spinner } from './ui/Spinner';
import { beatPlanRowsToText, countBeatPlanBlocks, parseBeatPlanText } from './beatPlanFormat';

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

const BEAT_SCRIPT_HELP =
  'One beat per paragraph — blank line between beats (Enter twice). '
  + 'Speaker [delivery]: dialogue [staging]. '
  + 'Stage: [Stage Direction] [emotion]: action [staging].';

export function BeatPlanModal({
  open,
  storySummary: initialSummary,
  beatsPlan: initialPlan,
  approveStatus,
  onClose,
  onApprove,
}: BeatPlanModalProps) {
  const [storySummary, setStorySummary] = useState(initialSummary);
  const [beatScript, setBeatScript] = useState('');

  useEffect(() => {
    if (open) {
      setStorySummary(initialSummary);
      setBeatScript(beatPlanRowsToText(initialPlan));
    }
  }, [open, initialSummary, initialPlan]);

  const handleApprove = () => {
    const beatsPlan = parseBeatPlanText(beatScript);
    if (beatsPlan.length === 0) return;
    onApprove(storySummary, beatsPlan);
  };

  const beatCount = countBeatPlanBlocks(beatScript);

  return (
    <Modal
      id="beat-plan"
      title="Review beat plan (edit before Approve)"
      panelClass="mn-modal-wide mn-modal-beat-plan"
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
            disabled={approveStatus === 'sending' || beatCount === 0}
            onClick={handleApprove}
          >
            {approveStatus === 'sending' ? (
              <><Spinner size="sm" inline /> Building Kling prompts…</>
            ) : 'Approve & populate beats'}
          </button>
        </>
      )}
    >
      <p class="mn-dim">
        Claude read the skeleton section for this video only. Edit the summary and beat script below,
        then Approve to generate rich Kling O3 prompts.
      </p>
      <label class="mn-label" for="beat-plan-summary">Story summary</label>
      <textarea
        id="beat-plan-summary"
        class="mn-textarea"
        data-testid="beat-plan-summary"
        rows={4}
        value={storySummary}
        onInput={(e) => setStorySummary((e.target as HTMLTextAreaElement).value)}
      />
      <label class="mn-label" for="beat-plan-script">
        Beat script
        {' '}
        <span class="mn-dim">({beatCount} beat{beatCount === 1 ? '' : 's'})</span>
      </label>
      <p class="mn-dim mn-text-sm">{BEAT_SCRIPT_HELP}</p>
      <textarea
        id="beat-plan-script"
        class="mn-textarea mn-beat-plan-script"
        data-testid="beat-plan-script"
        rows={14}
        spellcheck={false}
        value={beatScript}
        onInput={(e) => setBeatScript((e.target as HTMLTextAreaElement).value)}
        placeholder={'Lorelai [disbelieving]: WHAT IS THAT...? [eyes wide, rooted in place]\n\nArlo [to camera, warmly]: "Wanna try it?" [faces camera, gentle nod]'}
      />
    </Modal>
  );
}
