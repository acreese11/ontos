import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

const EN_MINOR_WORDS = new Set([
  'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'yet', 'so',
  'in', 'on', 'at', 'to', 'by', 'of', 'up', 'as', 'is', 'if',
  'vs', 'via', 'per',
]);

const CJK_LOCALES = new Set(['ja', 'zh', 'ko']);

function isAcronym(word: string): boolean {
  return word.length >= 2 && word === word.toUpperCase() && /^[A-Z0-9]+$/.test(word);
}

function capitalizeFirst(word: string): string {
  if (word.length === 0) return word;
  return word.charAt(0).toUpperCase() + word.slice(1);
}

function toTitleCase(label: string): string {
  return label
    .split(/\s+/)
    .map((word, i) => {
      if (isAcronym(word)) return word;
      const lower = word.toLowerCase();
      if (i > 0 && EN_MINOR_WORDS.has(lower)) return lower;
      return capitalizeFirst(lower);
    })
    .join(' ');
}

function toSentenceCase(label: string): string {
  if (label.length === 0) return label;
  return label
    .split(/\s+/)
    .map((word, i) => {
      if (isAcronym(word)) return word;
      if (i === 0) return capitalizeFirst(word.toLowerCase());
      return word.toLowerCase();
    })
    .join(' ');
}

/**
 * Format an ontology-derived label for display, applying locale-appropriate
 * casing rules. Preserves acronyms (all-caps words like "API").
 *
 * - English: title case (skip minor words except at start)
 * - Latin-script locales (de, fr, es, it, nl, …): sentence case
 * - CJK (ja, zh, ko): no transformation
 */
export function formatFieldLabel(label: string | null | undefined, locale?: string): string {
  if (!label) return '';

  const lang = (locale ?? 'en').split('-')[0].toLowerCase();

  if (CJK_LOCALES.has(lang)) return label;
  if (lang === 'en') return toTitleCase(label);
  return toSentenceCase(label);
}

/**
 * Hook that returns a stable `formatLabel` callback bound to the current
 * i18n language. Re-creates only when the language changes.
 */
export function useFormatLabel() {
  const { i18n } = useTranslation();
  const lang = i18n.language;
  return useCallback(
    (label: string | null | undefined) => formatFieldLabel(label, lang),
    [lang],
  );
}
