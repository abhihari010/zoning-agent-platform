import { useEffect, useState } from "react";
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

export function useSupabaseAuth({
  onAuthStateReset,
}: {
  onAuthStateReset: () => void;
}) {
  const [authSession, setAuthSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(authMode === "supabase");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authMessage, setAuthMessage] = useState("");
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const canLoadPrivateData = authMode === "supabase" ? Boolean(authSession) : true;

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
      setAuthSession(session);
      setAuthToken(session?.access_token ?? "");
      setAuthLoading(false);
    });

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      setAuthSession(session);
      setAuthToken(session?.access_token ?? "");
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

  async function signIn() {
    if (!supabase) {
      setAuthMessage("Supabase is not configured for this deployment.");
      return;
    }
    if (!authEmail.trim() || !authPassword) {
      setAuthMessage("Enter your email and password.");
      return;
    }

    setAuthLoading(true);
    setAuthMessage("");
    const { error: signInError } = await supabase.auth.signInWithPassword({
      email: authEmail.trim(),
      password: authPassword,
    });
    if (signInError) {
      setAuthMessage(signInError.message);
    }
    setAuthLoading(false);
  }

  async function signUp() {
    if (!supabase) {
      setAuthMessage("Supabase is not configured for this deployment.");
      return;
    }
    if (!authEmail.trim() || authPassword.length < 8) {
      setAuthMessage("Enter an email and a password with at least 8 characters.");
      return;
    }

    setAuthLoading(true);
    setAuthMessage("");
    const { error: signUpError } = await supabase.auth.signUp({
      email: authEmail.trim(),
      password: authPassword,
    });
    setAuthMessage(
      signUpError
        ? signUpError.message
        : "Account created. Check your email if confirmation is required, then sign in.",
    );
    setAuthLoading(false);
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
    authEmail,
    authPassword,
    authMessage,
    currentUser,
    setAuthEmail,
    setAuthPassword,
    signIn,
    signUp,
    signOut,
  };
}
