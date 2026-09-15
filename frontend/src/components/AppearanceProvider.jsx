import React, { createContext, useContext, useEffect } from 'react';

const AppearanceContext = createContext(null);

/*
 * ShimentoX uses one canonical visual theme.
 * The previous blue/classic theme has been removed from the UI.
 */
export function AppearanceProvider({ children }) {
  useEffect(() => {
    document.body.classList.add('theme-shimento');
    document.body.classList.remove('theme-classic');
  }, []);

  const value = {
    colorTheme: 'shimento',
    toggleColorTheme: () => {},
  };

  return (
    <AppearanceContext.Provider value={value}>
      {children}
    </AppearanceContext.Provider>
  );
}

export const useAppearance = () => useContext(AppearanceContext);
