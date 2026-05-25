import { createContext, useContext, useReducer, useCallback } from 'react';

const FilterContext = createContext(null);

const initialState = {
  market: 'NEM',
  region: 'NSW1',
  year: new Date().getFullYear(),
  quarter: 'ALL',
  dayType: 'ALL',
  months: ['ALL'],
};

function filterReducer(state, action) {
  switch (action.type) {
    case 'SET_FILTER': {
      const next = { ...state, [action.key]: action.value };
      // Derive market from region automatically
      if (action.key === 'region') {
        next.market = action.value === 'WEM' ? 'WEM' : 'NEM';
      }
      return next;
    }
    case 'RESET':
      return initialState;
    default:
      return state;
  }
}

/**
 * Convert filter state to API query parameters.
 * Only includes non-default values to keep requests clean.
 */
function toQueryParams(filters) {
  const params = { market: filters.market, region: filters.region };
  if (filters.year != null) {
    params.year = filters.year;
  }
  if (filters.quarter !== 'ALL') {
    params.quarter = filters.quarter;
  }
  if (filters.dayType !== 'ALL') {
    params.day_type = filters.dayType;
  }
  if (filters.months.length > 0 && !(filters.months.length === 1 && filters.months[0] === 'ALL')) {
    params.months = filters.months.join(',');
  }
  return params;
}

export function FilterProvider({ children }) {
  const [filters, dispatch] = useReducer(filterReducer, initialState);

  const setFilter = useCallback((key, value) => {
    dispatch({ type: 'SET_FILTER', key, value });
  }, []);

  const resetFilters = useCallback(() => {
    dispatch({ type: 'RESET' });
  }, []);

  const queryParams = toQueryParams(filters);

  return (
    <FilterContext.Provider value={{ filters, setFilter, resetFilters, toQueryParams: () => toQueryParams(filters), queryParams }}>
      {children}
    </FilterContext.Provider>
  );
}

export function useFilters() {
  const ctx = useContext(FilterContext);
  if (!ctx) throw new Error('useFilters must be used within FilterProvider');
  return ctx;
}
