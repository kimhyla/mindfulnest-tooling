import { useState } from 'preact/hooks';
import { PARENTHETICAL_SUGGESTIONS } from '../data/parenthetical_suggestions';

interface Props {
  onPick: (parenthetical: string) => void;  // caller inserts the picked text
  className?: string;
}

export function SuggestParentheticalDropdown({ onPick, className }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <div class={'suggest-paren-wrapper ' + (className || '')}
      data-testid="suggest-parenthetical-wrapper"
    >
      <button
        type="button"
        data-testid="suggest-parenthetical-button"
        onClick={() => setOpen((v) => !v)}
      >
        Suggest ▾
      </button>
      {open && (
        <div class="suggest-paren-menu" data-testid="suggest-parenthetical-menu">
          {PARENTHETICAL_SUGGESTIONS.map((s) => (
            <button
              key={s.emotion + s.species}
              type="button"
              data-testid={`suggest-parenthetical-option-${s.emotion}-${s.species}`}
              class="suggest-paren-option"
              onClick={() => {
                onPick(`(${s.text})`);
                setOpen(false);
              }}
            >
              <span class="emotion">{s.emotion}</span>
              <span class="species">[{s.species}]</span>
              <span class="preview">{s.text.slice(0, 50)}{s.text.length > 50 ? '…' : ''}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
