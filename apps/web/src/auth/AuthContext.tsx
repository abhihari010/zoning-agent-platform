import { createContext, useContext, type ReactNode } from "react";
import { authMode } from "../api";
import { useSupabaseAuth } from "../hooks/useSupabaseAuth";

type AuthValue = ReturnType<typeof useSupabaseAuth> & {
  /** True when the user may reach protected surfaces (always true off Supabase). */
  isAuthenticated: boolean;
};

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // Auth state lives once, above the router, so the marketing, auth, and
  // product shells all read a single session. Project/list resets are handled
  // by the product shell's own effect keyed on authSession, so nothing external
  // needs to fire here.
  const auth = useSupabaseAuth({ onAuthStateReset: () => {} });
  const isAuthenticated =
    authMode !== "supabase" || Boolean(auth.authSession);

  return (
    <AuthContext.Provider value={{ ...auth, isAuthenticated }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return value;
}
