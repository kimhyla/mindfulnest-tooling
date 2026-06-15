import { useEffect, useState } from 'preact/hooks';
import { Modal } from './ui/Modal';

const INSERT_SPEAKERS = [
  'Cedric', 'Arlo', 'Tessa', 'Lorelai', 'Benson',
] as const;

export interface InsertBeatPlanRow {
  speaker: string;
  dialogue_text: string;
  emotion: string;
  scene_notes: string;
  beat_type: 'dialogue';
}

export interface InsertBeatModalProps {
  open: boolean;
  afterBeatId: string;
  submitting: boolean;
  errorMessage?: string;
  onClose: () => void;
  onSubmit: (planRow: InsertBeatPlanRow) => void;
}

export function InsertBeatModal({
  open,
  afterBeatId,
  submitting,
  errorMessage,
  onClose,
  onSubmit,
}: InsertBeatModalProps) {
  const [speaker, setSpeaker] = useState<string>('Lorelai');
  const [dialogue, setDialogue] = useState('');
  const [emotion, setEmotion] = useState('neutral');
  const [sceneNotes, setSceneNotes] = useState('');

  useEffect(() => {
    if (open) {
      setSpeaker('Lorelai');
      setDialogue('');
      setEmotion('neutral');
      setSceneNotes('');
    }
  }, [open, afterBeatId]);

  const canSubmit = Boolean(
    speaker.trim()
    && dialogue.trim()
    && !submitting,
  );

  const handleSubmit = () => {
    if (!canSubmit) return;
    onSubmit({
      speaker: speaker.trim(),
      dialogue_text: dialogue.trim(),
      emotion: emotion.trim() || 'neutral',
      scene_notes: sceneNotes.trim(),
      beat_type: 'dialogue',
    });
  };

  return (
    <Modal
      id="bg-insert-beat"
      title="Insert beat"
      panelClass="mn-modal-wide"
      open={open}
      onClose={onClose}
      footer={(
        <>
          <button
            type="button"
            class="mn-btn"
            data-testid="bg-insert-cancel"
            onClick={onClose}
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="button"
            class="mn-btn mn-btn-primary"
            data-testid="bg-insert-submit"
            onClick={handleSubmit}
            disabled={!canSubmit}
          >
            {submitting ? 'Inserting…' : 'Insert beat'}
          </button>
        </>
      )}
    >
      <p class="mn-dim" data-testid="bg-insert-after-hint">
        New beat will appear after{' '}
        <strong>{afterBeatId || '(end of segment)'}</strong>.
        Speaker and dialogue are required — the beat is fully wired before it appears in the list.
      </p>
      {errorMessage ? (
        <p class="mn-bg-extract-error" role="alert" data-testid="bg-insert-error">
          {errorMessage}
        </p>
      ) : null}
      <label class="mn-field-label" for="bg-insert-speaker">
        Speaker
      </label>
      <select
        id="bg-insert-speaker"
        class="mn-beat-speaker"
        data-testid="bg-insert-speaker"
        value={speaker}
        onChange={(e) => setSpeaker((e.target as HTMLSelectElement).value)}
        disabled={submitting}
      >
        {INSERT_SPEAKERS.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
      <label class="mn-field-label" for="bg-insert-dialogue">
        Dialogue
      </label>
      <textarea
        id="bg-insert-dialogue"
        class="mn-bg-beat-text"
        data-testid="bg-insert-dialogue"
        rows={4}
        value={dialogue}
        onInput={(e) => setDialogue((e.target as HTMLTextAreaElement).value)}
        disabled={submitting}
        placeholder="Spoken line for this beat"
      />
      <label class="mn-field-label" for="bg-insert-emotion">
        Emotion
      </label>
      <input
        id="bg-insert-emotion"
        class="mn-input"
        data-testid="bg-insert-emotion"
        type="text"
        value={emotion}
        onInput={(e) => setEmotion((e.target as HTMLInputElement).value)}
        disabled={submitting}
      />
      <label class="mn-field-label" for="bg-insert-scene">
        Scene notes
      </label>
      <textarea
        id="bg-insert-scene"
        class="mn-bg-beat-text"
        data-testid="bg-insert-scene"
        rows={3}
        value={sceneNotes}
        onInput={(e) => setSceneNotes((e.target as HTMLTextAreaElement).value)}
        disabled={submitting}
        placeholder="Staging, framing, camera"
      />
    </Modal>
  );
}
