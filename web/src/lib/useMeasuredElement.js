import { useEffect, useRef, useState } from 'react';

export function useMeasuredElement() {
  const ref = useRef(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const node = ref.current;
    if (!node) {
      return undefined;
    }

    const updateSize = () => {
      const nextWidth = node.clientWidth || 0;
      const nextHeight = node.clientHeight || 0;
      setSize((current) => (
        current.width === nextWidth && current.height === nextHeight
          ? current
          : { width: nextWidth, height: nextHeight }
      ));
    };

    updateSize();

    const observer = new ResizeObserver(() => {
      updateSize();
    });
    observer.observe(node);

    return () => observer.disconnect();
  }, []);

  return [ref, size];
}
