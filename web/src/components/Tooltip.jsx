import { useState } from 'react';

/**
 * Lightweight hover tooltip for explaining financial/technical terms.
 * Renders inline — wrap any text that needs an explanation.
 * 
 * Usage:  <Tooltip term="IRR" explanation="内部收益率 — 使净现值为零的折现率">IRR</Tooltip>
 */
const Tooltip = ({ children, term, explanation, placement = 'top' }) => {
  const [show, setShow] = useState(false);

  if (!explanation) return children;

  const placementStyles = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  };

  return (
    <span
      className="relative inline-flex items-center cursor-help"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
      tabIndex={0}
      role="button"
      aria-describedby={show ? `tooltip-${term}` : undefined}
    >
      {children}
      <span className="ml-0.5 text-[var(--color-muted)] text-[10px] opacity-60 select-none">ⓘ</span>
      {show && (
        <span
          id={`tooltip-${term}`}
          role="tooltip"
          className={`absolute z-[100] ${placementStyles[placement] || placementStyles.top}
            px-3 py-2 text-xs font-sans font-normal leading-relaxed
            bg-[var(--color-inverted)] text-[var(--color-inverted-text)]
            rounded-lg shadow-lg whitespace-nowrap max-w-[280px]
            pointer-events-none animate-in fade-in duration-150`}
          style={{ whiteSpace: 'normal' }}
        >
          {term && <span className="font-semibold mr-1">{term}</span>}
          {explanation}
        </span>
      )}
    </span>
  );
};

export default Tooltip;
