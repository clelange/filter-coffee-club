import { tick } from 'svelte';
import type { Action } from 'svelte/action';

/** Keep native selection/keyboard behavior while revealing clipped option labels. */
export const selectedOption: Action<HTMLSelectElement, unknown> = (select) => {
  const summary = document.createElement('span');
  summary.className = 'selected-option';
  // Assistive technology already receives the full label from the native option.
  summary.setAttribute('aria-hidden', 'true');
  summary.hidden = true;
  select.after(summary);

  const context = document.createElement('canvas').getContext('2d');
  let destroyed = false;

  function measure() {
    if (destroyed) return;
    const option = select.selectedOptions[0];
    const text = option?.label.replace(/\s+/g, ' ').trim() ?? '';
    summary.textContent = text;
    if (!text || option?.disabled || !select.clientWidth) {
      summary.hidden = true;
      return;
    }

    const style = getComputedStyle(select);
    if (context) {
      context.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    }
    const letterSpacing = Number.parseFloat(style.letterSpacing) || 0;
    const textWidth = context
      ? context.measureText(text).width + letterSpacing * text.length
      : Infinity;
    // Native controls reserve space for their arrow in addition to CSS padding.
    const available =
      select.clientWidth -
      Number.parseFloat(style.paddingLeft) -
      Number.parseFloat(style.paddingRight) -
      24;
    summary.hidden = textWidth <= available;
  }

  function scheduleMeasure() {
    // A bound value or option list can change in the same Svelte update.
    void tick().then(measure);
  }

  const resizeObserver = new ResizeObserver(measure);
  resizeObserver.observe(select);
  const optionObserver = new MutationObserver(scheduleMeasure);
  optionObserver.observe(select, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ['label', 'selected']
  });
  select.addEventListener('change', scheduleMeasure);
  void document.fonts.ready.then(measure);
  scheduleMeasure();

  return {
    update: scheduleMeasure,
    destroy() {
      destroyed = true;
      resizeObserver.disconnect();
      optionObserver.disconnect();
      select.removeEventListener('change', scheduleMeasure);
      summary.remove();
    }
  };
};
