import { useEffect, useRef, useState } from "react";
import { createClient, type Session } from "@supabase/supabase-js";
import {
  authMode,
  fetchCurrentUser,
  setAuthToken,
  supabaseConfig,
  type CurrentUser,
} from "../api";

const supabase =
  authMode === "supabase" && supabaseConfig.url && supabaseConfig.anonKey
    ? createClient(supabaseConfig.url, supabaseConfig.anonKey)
    : null;

export type AuthResult = { ok: boolean; message?: string };

export function useSupabaseAuth({
  onAuthStateReset,
}: {
  onAuthStateReset: () => void;
}) {
  const [authSession, setAuthSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(authMode === "supabase");
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const canLoadPrivateData = authMode === "supabase" ? Boolean(authSession) : true;
  // Tracks the last access token we actually applied. Supabase re-emits auth
  // events (tab focus, periodic token checks) with a brand-new session object
  // even when the token is unchanged; applying each one churned authSession's
  // identity, and every data effect keys on authSession -> the admin page
  // refetched /sources, /status, /me, /projects in a loop (80+ requests/page)
  // and OOM'd the API. We only react to real token changes.
  const lastAccessTokenRef = useRef<string | null>(null);

  useEffect(() => {
    if (!supabase) {
      setAuthLoading(false);
      return;
    }

    let cancelled = false;
    supabase.auth.getSession().then(({ data }) => {
      if (cancelled) {
        return;
      }
      const session = data.session;
      const nextToken = session?.access_token ?? null;
      if (nextToken !== lastAccessTokenRef.current) {
        lastAccessTokenRef.current = nextToken;
        setAuthSession(session);
        setAuthToken(nextToken ?? "");
      }
      setAuthLoading(false);
    });

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      const nextToken = session?.access_token ?? null;
      if (nextToken === lastAccessTokenRef.current) {
        return;
      }
      lastAccessTokenRef.current = nextToken;
      setAuthSession(session);
      setAuthToken(nextToken ?? "");
      setCurrentUser(null);
      onAuthStateReset();
    });

    return () => {
      cancelled = true;
      subscription.subscription.unsubscribe();
    };
  }, [onAuthStateReset]);

  useEffect(() => {
    if (!canLoadPrivateData) {
      return;
    }

    let cancelled = false;

    async function loadCurrentUser() {
      try {
        const user = await fetchCurrentUser();
        if (!cancelled) {
          setCurrentUser(user);
        }
      } catch {
        if (!cancelled) {
          setCurrentUser(null);
        }
      }
    }

    void loadCurrentUser();
    return () => {
      cancelled = true;
    };
  }, [canLoadPrivateData, authSession]);

  async function signIn({
    email,
    password,
  }: {
    email: string;
    password: string;
  }): Promise<AuthResult> {
    if (!supabase) {
      return { ok: false, message: "Sign-in is not configured for this deployment." };
    }
    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });
    if (error) {
      return { ok: false, message: error.message };
    }
    return { ok: true };
  }

  async function signUp({
    name,
    email,
    password,
  }: {
    name?: string;
    email: string;
    password: string;
  }): Promise<AuthResult> {
    if (!supabase) {
      return { ok: false, message: "Sign-up is not configured for this deployment." };
    }
    const { data, error } = await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: name?.trim() ? { data: { full_name: name.trim() } } : undefined,
    });
    if (error) {
      return { ok: false, message: error.message };
    }
    // When email confirmation is required Supabase returns a user but no
    // session; surface that so the UI can tell the user to check their inbox.
    if (!data.session) {
      return {
        ok: true,
        message: "Account created. Check your email to confirm, then log in.",
      };
    }
    return { ok: true };
  }

  async function requestPasswordReset(email: string): Promise<AuthResult> {
    if (!supabase) {
      return { ok: false, message: "Password reset is not configured for this deployment." };
    }
    const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), {
      redirectTo: `${window.location.origin}/reset-password`,
    });
    if (error) {
      return { ok: false, message: error.message };
    }
    return { ok: true };
  }

  async function updatePassword(password: string): Promise<AuthResult> {
    if (!supabase) {
      return { ok: false, message: "Password reset is not configured for this deployment." };
    }
    const { error } = await supabase.auth.updateUser({ password });
    if (error) {
      return { ok: false, message: error.message };
    }
    return { ok: true };
  }

  async function signOut() {
    if (supabase) {
      await supabase.auth.signOut();
    }
    setAuthToken("");
    setCurrentUser(null);
    onAuthStateReset();
  }

  return {
    authSession,
    authLoading,
    currentUser,
    signIn,
    signUp,
    signOut,
    requestPasswordReset,
    updatePassword,
  };
}
