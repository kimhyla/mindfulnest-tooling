// Uncontrolled textarea helper — survives refresh/poll without cursor jumps or snap-back.
// Pattern matches StoryboardTab dialogue (contenteditable): DOM owns the value while
// typing; we only push externalText into the element when not focused/dirty/saving.

import { useCallback, useEffect, useLayoutEffect, useRef } from 'preact/hooks';
import type { RefObject } from 'preact';
import {
  clearPromptEdit,
  syncPromptEdit,
} from '../state/promptEditRegistry';

export interface UseProtectedPromptFieldOptions {
  fieldId: string;
  externalText: string;
  onSave: (text: string) => Promise<boolean>;
  debounceMs?: number;
  /** When true, mirror externalText in a read-only controlled textarea. */
  lockedExternal?: boolean;
}

export interface ProtectedPromptField {
  textareaRef: RefObject<HTMLTextAreaElement>;
  /** Non-null when generation lock — render controlled read-only textarea. */
  lockedValue: string | null;
  onFocus: () => void;
  onBlur: () => void;
  onInput: (e: Event) => void;
  setText: (text: string) => void;
  getText: () => string;
  flushSave: (text?: string) => Promise<boolean>;
}

function readText(
  el: HTMLTextAreaElement | null,
  fallback: string,
): string {
  return el?.value ?? fallback;
}

export function useProtectedPromptField({
  fieldId,
  externalText,
  onSave,
  debounceMs = 350,
  lockedExternal = false,
}: UseProtectedPromptFieldOptions): ProtectedPromptField {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dirtyRef = useRef(false);
  const focusedRef = useRef(false);
  const saveInFlightRef = useRef(false);
  const saveTimerRef = useRef<number | null>(null);
  const lastSavedRef = useRef(externalText);
  const textRef = useRef(externalText);

  const isEditing = useCallback((): boolean => (
    focusedRef.current
    || dirtyRef.current
    || saveInFlightRef.current
    || saveTimerRef.current !== null
  ), []);

  const publishRegistry = useCallback(() => {
    if (lockedExternal) {
      clearPromptEdit(fieldId);
      return;
    }
    if (!isEditing()) {
      clearPromptEdit(fieldId);
      return;
    }
    syncPromptEdit(fieldId, {
      text: textRef.current,
      dirty: dirtyRef.current,
      focused: focusedRef.current,
      saveInFlight: saveInFlightRef.current,
    });
  }, [fieldId, isEditing, lockedExternal]);

  // Seed DOM when beat/field changes (or first mount).
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el || lockedExternal) return;
    el.value = externalText;
    textRef.current = externalText;
    lastSavedRef.current = externalText;
    dirtyRef.current = false;
    clearPromptEdit(fieldId);
  }, [fieldId]);

  // Adopt server text only when the user is not actively editing.
  useLayoutEffect(() => {
    if (lockedExternal) return;
    if (isEditing()) return;
    const el = textareaRef.current;
    if (!el) return;
    if (el.value === externalText) {
      textRef.current = externalText;
      lastSavedRef.current = externalText;
      return;
    }
    el.value = externalText;
    textRef.current = externalText;
    lastSavedRef.current = externalText;
  }, [externalText, fieldId, isEditing, lockedExternal]);

  const flushSave = useCallback(async (textOverride?: string): Promise<boolean> => {
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const text = textOverride ?? readText(textareaRef.current, textRef.current);
    textRef.current = text;
    if (text === lastSavedRef.current) {
      if (!focusedRef.current) dirtyRef.current = false;
      publishRegistry();
      return true;
    }
    saveInFlightRef.current = true;
    publishRegistry();
    try {
      const ok = await onSave(text);
      if (ok) {
        lastSavedRef.current = text;
        if (!focusedRef.current) {
          dirtyRef.current = false;
          clearPromptEdit(fieldId);
        } else {
          dirtyRef.current = true;
          publishRegistry();
        }
      } else {
        publishRegistry();
      }
      return ok;
    } finally {
      saveInFlightRef.current = false;
      publishRegistry();
    }
  }, [fieldId, onSave, publishRegistry]);

  const scheduleSave = useCallback((text: string) => {
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current);
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null;
      publishRegistry();
      void flushSave(text);
    }, debounceMs);
    publishRegistry();
  }, [debounceMs, flushSave, publishRegistry]);

  const onInput = useCallback((e: Event) => {
    if (lockedExternal) return;
    const t = (e.target as HTMLTextAreaElement).value;
    textRef.current = t;
    dirtyRef.current = true;
    scheduleSave(t);
  }, [lockedExternal, scheduleSave]);

  const onFocus = useCallback(() => {
    focusedRef.current = true;
    publishRegistry();
  }, [publishRegistry]);

  const onBlur = useCallback(() => {
    focusedRef.current = false;
    publishRegistry();
    void flushSave();
  }, [flushSave, publishRegistry]);

  const setText = useCallback((text: string) => {
    if (lockedExternal) return;
    const el = textareaRef.current;
    if (el) el.value = text;
    textRef.current = text;
    dirtyRef.current = true;
    scheduleSave(text);
  }, [lockedExternal, scheduleSave]);

  const getText = useCallback(
    () => readText(textareaRef.current, textRef.current),
    [],
  );

  useEffect(() => () => {
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current);
  }, []);

  return {
    textareaRef,
    lockedValue: lockedExternal ? externalText : null,
    onFocus,
    onBlur,
    onInput,
    setText,
    getText,
    flushSave,
  };
}
