"use client";

import { useState, useTransition } from "react";
import type { StudyChatResponse } from "@gal-learner/shared";

import { requestStudyReply } from "./mock-api";

interface AskStudyInput {
  message: string;
  personaId: string;
  sectionId: string;
}

export function useStudySession() {
  const [session, setSession] = useState<StudyChatResponse | null>(null);
  const [isPending, startTransition] = useTransition();

  const ask = (input: AskStudyInput) => {
    startTransition(async () => {
      const next = await requestStudyReply(input);
      setSession(next);
    });
  };

  return {
    session,
    isPending,
    ask
  };
}
