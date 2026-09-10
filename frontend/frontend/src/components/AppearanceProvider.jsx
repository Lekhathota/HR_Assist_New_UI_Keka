import React, { createContext, useContext, useEffect, useState } from 'react';

const AppearanceContext = createContext(null);

// Preserve the existing preference keys and migration on public pages too.
export function AppearanceProvider({ children }) {
  const [colorTheme, setColorTheme] = useState(() => {
    if (localStorage.getItem('color_theme_version') !== 'ember-v1') {
      localStorage.setItem('color_theme_version', 'ember-v1');
      localStorage.setItem('color_theme', 'warm');
      return 'warm';
    }
    return localStorage.getItem('color_theme') || 'warm';
  });

  useEffect(() => {
    document.body.classList.toggle('theme-warm', colorTheme === 'warm');
  }, [colorTheme]);

  const toggleColorTheme = () => {
    const next = colorTheme === 'warm' ? 'classic' : 'warm';
    localStorage.setItem('color_theme', next);
    setColorTheme(next);
  };

  return (
    <AppearanceContext.Provider value={{ colorTheme, toggleColorTheme }}>
      {children}
    </AppearanceContext.Provider>
  );
}

export const useAppearance = () => useContext(AppearanceContext);
