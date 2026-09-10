"use client";

import { useEffect, useRef, useState } from "react";
import type { PersonaCard, ModelRecovery } from "@vibe-learner/shared";
import { generatePersonaCards } from "../lib/data/persona-cards";
import { AsyncResultFence, type AsyncResultScope, type AsyncResultTicket } from "../lib/async-result-fence";
import { isApiHttpError } from "../lib/http-error";
import { buildDraftWithInsertedCards, collectReferenceHintsFromCards } from "../lib/persona-editor-model";
import { clearPersonaDraftForGeneratedBackfill, mergeReferenceHints, type PersonaDraft } from "../lib/persona-draft";

interface GeneratedPersonaMeta {
  summary: string;
  relationship: string;
  learnerAddress: string;
}

type CardGenerationMode = "keywords" | "long_text";

export function usePersonaCardGeneration({ draft, updatePersonaDraft, currentPersonaAsyncScope }: {
  draft: PersonaDraft;
  updatePersonaDraft: (draft: PersonaDraft) => void;
  currentPersonaAsyncScope: (fieldTarget: string) => AsyncResultScope;
}, generate = generatePersonaCards) {
  const [generatedCards, setGeneratedCards] = useState<PersonaCard[]>([]);
  const [cardGenerationMode, setCardGenerationMode] = useState<CardGenerationMode>("keywords");
  const [cardKeywordInput, setCardKeywordInput] = useState("");
  const [cardLongTextFile, setCardLongTextFile] = useState<File | null>(null);
  const [cardGenerateCount, setCardGenerateCount] = useState("");
  const [clearBeforeBackfill, setClearBeforeBackfill] = useState(false);
  const [cardActionPending, setCardActionPending] = useState<null | "generate_keywords" | "generate_long_text">(null);
  const [cardMessage, setCardMessage] = useState("");
  const [cardError, setCardError] = useState("");
  const [cardModelRecoveries, setCardModelRecoveries] = useState<ModelRecovery[]>([]);
  const [generatedPersonaMeta, setGeneratedPersonaMeta] = useState<GeneratedPersonaMeta>({
    summary: "",
    relationship: "",
    learnerAddress: "",
  });

  const cardGenerationFenceRef = useRef(new AsyncResultFence());
  const mountedRef = useRef(true);
  const canApply = (ticket: AsyncResultTicket) => mountedRef.current && cardGenerationFenceRef.current.decide(ticket, currentPersonaAsyncScope("persona-card-candidate")) === "apply";
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; cardGenerationFenceRef.current.invalidate(); };
  }, []);
  function resetCardGeneration() {
    cardGenerationFenceRef.current.invalidate();
    setCardActionPending(null);
    setGeneratedCards([]);
    setGeneratedPersonaMeta({ summary: "", relationship: "", learnerAddress: "" });
    setCardMessage(""); setCardError(""); setCardModelRecoveries([]);
  }
  function applyGeneratedCardsToDraft() {
    if (!generatedCards.length && !generatedPersonaMeta.summary && !generatedPersonaMeta.relationship && !generatedPersonaMeta.learnerAddress) {
      setCardError("当前没有可回填的生成人格内容。");
      return;
    }
    if (
      clearBeforeBackfill &&
      !window.confirm("应用后会清空现有摘要、关系、称呼、参考提示和全部插槽。是否继续？")
    ) {
      return;
    }
    setCardError("");
    setCardMessage("");
    const baseDraft = clearBeforeBackfill
      ? clearPersonaDraftForGeneratedBackfill(draft)
      : draft;
    const insertion = buildDraftWithInsertedCards(baseDraft, generatedCards);
    updatePersonaDraft({
      ...insertion.draft,
      summary: generatedPersonaMeta.summary || insertion.draft.summary,
      relationship: generatedPersonaMeta.relationship || insertion.draft.relationship,
      learnerAddress: generatedPersonaMeta.learnerAddress || insertion.draft.learnerAddress,
      referenceHints: mergeReferenceHints(
        insertion.draft.referenceHints,
        collectReferenceHintsFromCards(generatedCards)
      ),
    });
    const metaParts = [
      generatedPersonaMeta.summary ? "摘要" : "",
      generatedPersonaMeta.relationship ? "关系" : "",
      generatedPersonaMeta.learnerAddress ? "称呼" : "",
    ].filter(Boolean);
    const summary = [
      clearBeforeBackfill ? "已清空摘要、关系、称呼、参考提示和全部插槽" : "",
      metaParts.length ? `已回填${metaParts.join("、")}` : "",
      insertion.insertedCount ? `并插入 ${insertion.insertedCount} 张卡片` : generatedCards.length ? "卡片已存在，未重复插入" : "",
    ].filter(Boolean).join("，");
    setCardMessage(summary || "已将本轮生成内容应用到当前编辑区。");
  }

  function insertCardsIntoDraft(cards: PersonaCard[], insertIndex?: number) {
    if (!cards.length) {
      setCardError("请先选择至少一张人格卡片。");
      return;
    }
    setCardError("");
    setCardMessage("");
    const insertion = buildDraftWithInsertedCards(draft, cards, insertIndex);
    updatePersonaDraft({
      ...insertion.draft,
      referenceHints: mergeReferenceHints(
        insertion.draft.referenceHints,
        collectReferenceHintsFromCards(cards)
      ),
    });
    if (!insertion.insertedCount) {
      setCardMessage("所选卡片已存在于当前人格中，未重复插入。");
      return;
    }
    setCardMessage(`已将 ${insertion.insertedCount} 张卡片插入当前人格编辑区。`);
  }

  async function handleGenerateCards(mode: "keywords" | "long_text") {
    if (!mountedRef.current) return;
    const requestScope = currentPersonaAsyncScope("persona-card-candidate");
    const ticket = cardGenerationFenceRef.current.begin(requestScope);
    setCardError("");
    setCardMessage("");
    setCardModelRecoveries([]);
    setCardActionPending(mode === "keywords" ? "generate_keywords" : "generate_long_text");
    try {
      let inputText = "";
      if (mode === "keywords") {
        inputText = cardKeywordInput.trim();
      } else {
        if (!cardLongTextFile) {
          setCardError("请先上传纯文本文件。");
          return;
        }
        try {
          inputText = (await cardLongTextFile.text()).trim();
        } catch (error) {
          if (canApply(ticket)) setCardError(`读取文本文件失败：${String(error)}`);
          return;
        }
      }
      if (!canApply(ticket)) return;
      if (!inputText) {
        setCardError(mode === "keywords" ? "请先输入关键词。" : "上传的文本文件为空。");
        return;
      }
      const countText = cardGenerateCount.trim();
      let count: number | null = null;
      if (countText) {
        const parsedCount = Number(countText);
        if (!Number.isInteger(parsedCount) || parsedCount < 1 || parsedCount > 24) {
          setCardError("精确卡片数量必须是 1 到 24 的整数，或留空交给模型决定。");
          return;
        }
        count = parsedCount;
      }
      const result = await generate({
        mode,
        inputText,
        count,
      });
      if (!canApply(ticket)) {
        return;
      }
      setGeneratedCards(result.items);
      setGeneratedPersonaMeta({
        summary: result.summary,
        relationship: result.relationship,
        learnerAddress: result.learnerAddress,
      });
      setCardModelRecoveries(result.modelRecoveries ?? []);
      setCardMessage(
        `已生成 ${result.items.length} 张卡片。${
          result.usedWebSearch
            ? "已使用联网搜索。"
            : result.usedModel === "mock"
              ? "本地模拟结果。"
              : ""
        }`
      );
    } catch (error) {
      if (canApply(ticket)) {
        setCardError(humanizePersonaCardGenerationError(error));
      }
    } finally {
      if (cardGenerationFenceRef.current.settle(ticket)) {
        setCardActionPending(null);
      }
    }
  }

  return {
    generatedCards,
    cardGenerationMode,
    setCardGenerationMode,
    cardKeywordInput,
    setCardKeywordInput,
    cardLongTextFile,
    setCardLongTextFile,
    cardGenerateCount,
    setCardGenerateCount,
    clearBeforeBackfill,
    setClearBeforeBackfill,
    cardActionPending,
    cardMessage,
    setCardMessage,
    cardError,
    setCardError,
    cardModelRecoveries,
    generatedPersonaMeta,
    applyGeneratedCardsToDraft,
    insertCardsIntoDraft,
    handleGenerateCards,
    resetCardGeneration,
  };
}

function humanizePersonaCardGenerationError(error: unknown): string {
  if (!isApiHttpError(error)) {
    return "人格卡片生成失败，请稍后重试。";
  }
  const code = error.code || error.message;
  if (code === "setting_persona_card_count_mismatch") {
    return "模型返回的卡片数量不符合精确数量要求，请重试或调整数量。";
  }
  if (code === "keyword_generation_requires_openai") {
    return "当前提供器暂不支持关键词生成，请切换提供器或使用长文本提取。";
  }
  if (error.status === 422) {
    return "生成条件未通过校验，请检查关键词和精确卡片数量。";
  }
  return "人格卡片生成失败，请稍后重试。";
}

