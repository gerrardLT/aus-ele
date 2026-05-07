import { useEffect, useRef, useState } from 'react';

import { shouldActivateDeferredSection } from '../lib/sectionVisibility';

export default function DeferredSection({
  children,
  fallback,
  className = '',
  rootMargin = '240px 0px',
  threshold = 0.01,
}) {
  const sectionRef = useRef(null);
  const [isVisible, setIsVisible] = useState(false);
  const [hasActivated, setHasActivated] = useState(false);

  useEffect(() => {
    const node = sectionRef.current;
    if (!node || hasActivated) {
      return undefined;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        const nextVisible = entry.isIntersecting;
        setIsVisible(nextVisible);
        if (shouldActivateDeferredSection({ isVisible: nextVisible, hasActivated })) {
          setHasActivated(true);
        }
      },
      {
        rootMargin,
        threshold,
      },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [hasActivated, rootMargin, threshold]);

  return (
    <div ref={sectionRef} className={className}>
      {hasActivated ? children : fallback}
    </div>
  );
}
