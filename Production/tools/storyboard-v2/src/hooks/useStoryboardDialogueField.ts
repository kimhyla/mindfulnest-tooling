/**
 * useStoryboardDialogueField — OPERATOR_EDIT_AUTHORITY_V1 contenteditable dialogue cell.
 */
import { useCallback, useLayoutEffect, useRef } from 'preact/hooks';
import type { RefObject } from 'preact';
import {
  clearPromptEdit,
  isPromptEditProtected,
  syncPromptEdit,
} from '../state/promptEditRegistry.ts';

export const STORYBOARD_DIALOGUE_FIELD_V1 = 'STORYBOARD_DIALOGUE_FIELD_V1';

const SHADOW_TTL_MS = 24 * 3600 * 1000;

function shadowKey(eventId: string, beatId: string): string {
  return `mn:v59:dialogue-shadow:${eventId}:${beatId}`;
}

export function readStoryboardDialogueShadow(
  eventId: string,
  beatId: string,
): string | null {
  try {
    const raw = localStorage.getItem(shadowKey(eventId, beatId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { text: string; ts: number };
    if (Date.now() - parsed.ts > SHADOW_TTL_MS) {
      localStorage.removeItem(shadowKey(eventId, beatId));
      return null;
    }
    return parsed.text;
  } catch {
    return null;
  }
}

export function writeStoryboardDialogueShadow(
  eventId: string,
  beatId: string,
  text: string,
): void {
  try {
    localStorage.setItem(
      shadowKey(eventId, beatId),
      JSON.stringify({ text, ts: Date.now() }),
    );
  } catch {
    // best-effort
  }
}

export function clearStoryboardDialogueShadow(
  eventId: string,
  beatId: string,
): void {
  try {
    localStorage.removeItem(shadowKey(eventId, beatId));
  } catch {
    // ignore
  }
}

export interface UseStoryboardDialogueFieldOptions {
  eventId: string;
  beatId: string;
  externalText: string;
}

export interface StoryboardDialogueFieldController {
  editRef: RefObject<HTMLParagraphElement>;
  onInput: () => void;
  onFocus: () => void;
  onBlur: () => void;
  readText: () => string;
  setDomText: (text: string) => void;
  isEditing: () => boolean;
}

export function useStoryboardDialogueField({
  eventId,
  beatId,
  externalText,
}: UseStoryboardDialogueFieldOptions): StoryboardDialogueFieldController {
  const editRef = useRef<HTMLParagraphElement | null>(null);
  const fieldId = `sb_dialogue_${eventId}_${beatId}`;
  const focusedRef = useRef(false);
  const dirtyRef = useRef(false);
  const textRef = useRef(externalText);

  const publishRegistry = useCallback(() => {
    if (!focusedRef.current && !dirtyRef.current) {
      clearPromptEdit(fieldId);
      return;
    }
    syncPromptEdit(fieldId, {
      text: textRef.current,
      dirty: dirtyRef.current,
      focused: focusedRef.current,
      saveInFlight: false,
    });
  }, [fieldId]);

  const isEditing = useCallback(
    () => focusedRef.current || dirtyRef.current || isPromptEditProtected(fieldId),
    [fieldId],
  );

  useLayoutEffect(() => {
    const el = editRef.current;
    if (!el) return;
    const shadow = readStoryboardDialogueShadow(eventId, beatId);
    const seed = shadow !== null && shadow !== externalText ? shadow : externalText;
    el.innerText = seed;
    textRef.current = seed;
    dirtyRef.current = shadow !== null && shadow !== externalText;
    publishRegistry();
  }, [beatId, eventId]);

  useLayoutEffect(() => {
    if (isEditing()) return;
    const el = editRef.current;
    if (!el) return;
    if (el.innerText === externalText) {
      textRef.current = externalText;
      return;
    }
    el.innerText = externalText;
    textRef.current = externalText;
    dirtyRef.current = false;
    clearPromptEdit(fieldId);
  }, [externalText, fieldId, isEditing]);

  const readText = useCallback(
    () => editRef.current?.innerText ?? textRef.current,
    [],
  );

  const setDomText = useCallback((text: string) => {
    if (editRef.current) editRef.current.innerText = text;
    textRef.current = text;
    dirtyRef.current = true;
    publishRegistry();
  }, [publishRegistry]);

  const onInput = useCallback(() => {
    const next = editRef.current?.innerText ?? '';
    textRef.current = next;
    dirtyRef.current = true;
    writeStoryboardDialogueShadow(eventId, beatId, next);
    publishRegistry();
  }, [beatId, eventId, publishRegistry]);

  const onFocus = useCallback(() => {
    focusedRef.current = true;
    publishRegistry();
  }, [publishRegistry]);

  const onBlur = useCallback(() => {
    focusedRef.current = false;
    publishRegistry();
  }, [publishRegistry]);

  return {
    editRef,
    onInput,
    onFocus,
    onBlur,
    readText,
    setDomText,
    isEditing,
  };
}
