import { useState } from "react";
import { submitFeedback, type IntakeResponse } from "../api";
import type { FeedbackState } from "../types/app";

export function useFeedback(intake: IntakeResponse | null) {
  const [feedbackNote, setFeedbackNote] = useState("");
  const [feedbackState, setFeedbackState] = useState<FeedbackState>("idle");
  const [feedbackMessage, setFeedbackMessage] = useState("");

  async function onSubmitFeedback(helpful: boolean) {
    if (!intake || feedbackState === "submitting") {
      return;
    }

    try {
      setFeedbackState("submitting");
      await submitFeedback({
        projectId: intake.projectId,
        helpful,
        comment: feedbackNote,
      });
      setFeedbackState("submitted");
      setFeedbackMessage(
        helpful
          ? "Thanks. That tells us the workflow is landing in the right place."
          : "Thanks. Weâ€™ll treat that as a signal to tighten the workflow.",
      );
    } catch (feedbackError) {
      setFeedbackState("idle");
      setFeedbackMessage(
        feedbackError instanceof Error
          ? feedbackError.message
          : "Feedback submission failed.",
      );
    }
  }

  function resetFeedback() {
    setFeedbackNote("");
    setFeedbackState("idle");
    setFeedbackMessage("");
  }

  return {
    feedbackNote,
    setFeedbackNote,
    feedbackState,
    feedbackMessage,
    onSubmitFeedback,
    resetFeedback,
  };
}
