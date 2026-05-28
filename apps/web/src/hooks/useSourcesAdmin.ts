import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import {
  clearAdminAccessKey,
  fetchJurisdictionRequestSummaries,
  fetchSourceIndexStatus,
  getAdminAccessKey,
  importLocalDocuments,
  importSourcePacks,
  listSources,
  reindexSources,
  saveSource,
  setAdminAccessKey,
  type JurisdictionRequestSummary,
  type SourceIndexStatus,
  type SourceRegistryEntry,
} from "../api";
import type { Workspace } from "../types/app";
import { emptySourceForm } from "../utils/sourceForms";

export function useSourcesAdmin({
  canLoadPrivateData,
  canUseAdminTools,
  authSession,
  onWorkspaceChange,
}: {
  canLoadPrivateData: boolean;
  canUseAdminTools: boolean;
  authSession: Session | null;
  onWorkspaceChange: (workspace: Workspace) => void;
}) {
  const [sources, setSources] = useState<SourceRegistryEntry[]>([]);
  const [indexStatus, setIndexStatus] = useState<SourceIndexStatus | null>(null);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourceForm, setSourceForm] = useState<SourceRegistryEntry>(emptySourceForm);
  const [sourceMessage, setSourceMessage] = useState("");
  const [sourceSaving, setSourceSaving] = useState(false);
  const [jurisdictionRequests, setJurisdictionRequests] = useState<JurisdictionRequestSummary[]>([]);
  const [jurisdictionRequestsLoading, setJurisdictionRequestsLoading] = useState(false);
  const [jurisdictionRequestsMessage, setJurisdictionRequestsMessage] = useState("");
  const [reindexMessage, setReindexMessage] = useState("");
  const [importDirectory, setImportDirectory] = useState("");
  const [importing, setImporting] = useState(false);
  const [importMessage, setImportMessage] = useState("");
  const [adminAccessKey, setStoredAdminAccessKey] = useState(() => getAdminAccessKey());
  const [adminAccessInput, setAdminAccessInput] = useState("");
  const [adminAccessMessage, setAdminAccessMessage] = useState("");

  useEffect(() => {
    if (!canLoadPrivateData || !canUseAdminTools) {
      setJurisdictionRequests([]);
      setJurisdictionRequestsMessage("");
      setJurisdictionRequestsLoading(false);
      return;
    }

    let cancelled = false;

    async function loadJurisdictionRequests() {
      try {
        setJurisdictionRequestsLoading(true);
        const summaries = await fetchJurisdictionRequestSummaries();
        if (!cancelled) {
          setJurisdictionRequests(summaries);
          setJurisdictionRequestsMessage("");
        }
      } catch (requestError) {
        if (!cancelled) {
          setJurisdictionRequests([]);
          setJurisdictionRequestsMessage(
            requestError instanceof Error
              ? requestError.message
              : "Failed to load jurisdiction requests.",
          );
        }
      } finally {
        if (!cancelled) {
          setJurisdictionRequestsLoading(false);
        }
      }
    }

    void loadJurisdictionRequests();
    return () => {
      cancelled = true;
    };
  }, [canLoadPrivateData, canUseAdminTools, authSession, adminAccessKey]);

  useEffect(() => {
    if (!canLoadPrivateData) {
      return;
    }

    let cancelled = false;

    async function loadSources() {
      try {
        setSourcesLoading(true);
        const [nextSources, nextIndexStatus] = await Promise.all([
          listSources(),
          fetchSourceIndexStatus(),
        ]);
        if (!cancelled) {
          setSources(nextSources);
          setIndexStatus(nextIndexStatus);
        }
      } catch (loadError) {
        if (!cancelled) {
          setSourceMessage(
            loadError instanceof Error ? loadError.message : "Failed to load sources.",
          );
        }
      } finally {
        if (!cancelled) {
          setSourcesLoading(false);
        }
      }
    }

    void loadSources();
    return () => {
      cancelled = true;
    };
  }, [canLoadPrivateData, authSession]);

  async function refreshSources(message?: string) {
    const [nextSources, nextIndexStatus] = await Promise.all([
      listSources(),
      fetchSourceIndexStatus(),
    ]);
    setSources(nextSources);
    setIndexStatus(nextIndexStatus);
    if (message) {
      setSourceMessage(message);
    }
  }

  function saveAdminKey() {
    if (!adminAccessInput.trim()) {
      setAdminAccessMessage("Enter the source admin key to enable write actions.");
      return;
    }

    setAdminAccessKey(adminAccessInput);
    setStoredAdminAccessKey(adminAccessInput.trim());
    setAdminAccessInput("");
    setAdminAccessMessage("Source admin key saved for this browser session.");
  }

  function clearStoredAdminKey() {
    clearAdminAccessKey();
    setStoredAdminAccessKey("");
    setAdminAccessInput("");
    setAdminAccessMessage("Source admin key cleared. Source status and catalog remain visible.");
  }

  async function onSaveSource() {
    if (
      !sourceForm.sourceId.trim() ||
      !sourceForm.title.trim() ||
      !sourceForm.excerpt.trim() ||
      !sourceForm.sectionRef.trim()
    ) {
      setSourceMessage("Source ID, title, excerpt, and section reference are required.");
      return;
    }

    try {
      setSourceSaving(true);
      setSourceMessage("");
      const saved = await saveSource({
        ...sourceForm,
        sourceId: sourceForm.sourceId.trim(),
        title: sourceForm.title.trim(),
        excerpt: sourceForm.excerpt.trim(),
        sectionRef: sourceForm.sectionRef.trim(),
      });
      setSources(saved);
      setIndexStatus(await fetchSourceIndexStatus());
      setSourceForm(emptySourceForm());
      setSourceMessage("Source saved.");
    } catch (saveError) {
      setSourceMessage(
        saveError instanceof Error ? saveError.message : "Failed to save source.",
      );
    } finally {
      setSourceSaving(false);
    }
  }

  async function onReindexSources() {
    try {
      setReindexMessage("");
      const summary = await reindexSources();
      setReindexMessage(
        `Reindex ${summary.status}. ${summary.sourceCount} sources produced ${summary.chunkCount} chunks and ${summary.vectorCount} vectors.`,
      );
      await refreshSources();
    } catch (reindexError) {
      setReindexMessage(
        reindexError instanceof Error
          ? reindexError.message
          : "Failed to request reindex.",
      );
    }
  }

  async function onImportDocuments() {
    try {
      setImporting(true);
      setImportMessage("");
      const importResult = await importLocalDocuments(importDirectory);
      await refreshSources(
        `Imported ${importResult.importedCount} document(s). ${importResult.sourceCount} sources now available.`,
      );
      setImportMessage(
        importResult.importedSourceIds.length > 0
          ? `Imported: ${importResult.importedSourceIds.join(", ")}`
          : "No documents were imported.",
      );
    } catch (importError) {
      setImportMessage(
        importError instanceof Error
          ? importError.message
          : "Failed to import local documents.",
      );
    } finally {
      setImporting(false);
    }
  }

  async function onImportSourcePacks() {
    try {
      setImporting(true);
      setImportMessage("");
      const importResult = await importSourcePacks(importDirectory);
      await refreshSources(
        `Imported ${importResult.importedCount} source-pack record(s). ${importResult.sourceCount} sources now available.`,
      );
      setImportMessage(
        importResult.importedSourceIds.length > 0
          ? `Imported source packs: ${importResult.importedSourceIds.join(", ")}`
          : "No source-pack records were imported.",
      );
    } catch (importError) {
      setImportMessage(
        importError instanceof Error
          ? importError.message
          : "Failed to import source packs.",
      );
    } finally {
      setImporting(false);
    }
  }

  function loadSourceIntoForm(source: SourceRegistryEntry) {
    onWorkspaceChange("admin");
    setSourceForm(source);
    setSourceMessage(`Loaded ${source.sourceId} into the editor.`);
  }

  function resetSourceState() {
    setSourceMessage("");
    setSources([]);
    setIndexStatus(null);
  }

  return {
    sources,
    indexStatus,
    sourcesLoading,
    sourceForm,
    setSourceForm,
    sourceMessage,
    sourceSaving,
    jurisdictionRequests,
    jurisdictionRequestsLoading,
    jurisdictionRequestsMessage,
    reindexMessage,
    importDirectory,
    setImportDirectory,
    importing,
    importMessage,
    adminAccessKey,
    adminAccessInput,
    setAdminAccessInput,
    adminAccessMessage,
    saveAdminKey,
    clearStoredAdminKey,
    onSaveSource,
    onReindexSources,
    onImportDocuments,
    onImportSourcePacks,
    loadSourceIntoForm,
    resetSourceState,
  };
}
