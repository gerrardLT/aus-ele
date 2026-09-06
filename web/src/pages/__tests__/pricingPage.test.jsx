import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PricingPage from '../../pages/PricingPage';

// 注意：onboarding 模块在 vitest 中通过 @vitejs/plugin-react 的 resolve 会失败，
// 因此在 PricingPage.jsx 中有 catch(() => {}) 兜底。无需额外 mock。

describe('PricingPage', () => {
  describe('P0 crash regression（2026-08-24 WQS audit）', () => {
    test('Renders three plans without crash (features.map fix)', () => {
      // Before fix: t.features.map → Cannot read properties of undefined (reading 'map')
      // After fix: use plan.features[zh/en] correctly.
      const { container } = render(<PricingPage />);
      // Pricing page has two h1s - match the longer Chinese one in hero section
      const h1 = screen.getByText(/储能市场进入|BESS Investment Decision Platform/s);
      expect(h1).toBeInTheDocument();
      // Three pricing cards present
      const sections = container.querySelectorAll('section.rounded-2xl');
      expect(sections).toHaveLength(3);
      const allFeatures = Array.from(container.querySelectorAll('li.flex'))
        .map(node => node.textContent.trim())
        .filter(Boolean);
      expect(allFeatures.length).toBeGreaterThan(9); // Starter/Growth/Pro each has 4 features
    });
  });
});
