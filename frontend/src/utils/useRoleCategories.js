import { useEffect, useMemo, useState } from 'react';
import { apiGet } from '../api.js';

let cached = null;

/**
 * Role categories from the backend taxonomy (/api/meta/role-categories).
 * Until it loads, or if it can't, falls back to the categories present in `values`.
 */
export function useRoleCategories(values = []) {
  const [categories, setCategories] = useState(cached);
  useEffect(() => {
    if (cached) return undefined;
    let cancelled = false;
    apiGet('/api/meta/role-categories')
      .then(data => {
        if (cancelled || !Array.isArray(data?.categories)) return;
        cached = data.categories;
        setCategories(cached);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);
  const fromData = useMemo(
    () => [...new Set(values.map(value => String(value || '').trim()).filter(Boolean))].sort(),
    [values],
  );
  return categories?.length ? categories : fromData;
}
