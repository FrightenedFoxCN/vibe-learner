"use client";

import { useId } from "react";
import { OUTPUT_LANGUAGE_OPTIONS, outputLanguageError } from "../lib/output-language";

export function OutputLanguageField({
  value,
  onChange,
  disabled,
  study = false,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  study?: boolean;
}) {
  const id = useId();
  const known = OUTPUT_LANGUAGE_OPTIONS.some(([code]) => code === value);
  const error = outputLanguageError(value);
  return (
    <div className="output-language-field">
      <label htmlFor={id}>输出语言</label>
      <select
        id={id}
        value={known ? value : "custom"}
        onChange={(event) =>
          onChange(event.target.value === "custom" ? "" : event.target.value)
        }
        disabled={disabled}
        aria-describedby={`${id}-help`}
      >
        {OUTPUT_LANGUAGE_OPTIONS.map(([code, label]) => (
          <option key={code} value={code}>
            {label}
          </option>
        ))}
        <option value="custom">其他语言标签…</option>
      </select>
      {!known && (
        <input
          aria-label="输出语言标签"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="fr-CA"
          maxLength={35}
          disabled={disabled}
          aria-invalid={Boolean(error)}
          aria-describedby={`${id}-help`}
        />
      )}
      <small id={`${id}-help`}>
        {study
          ? "自动沿用计划语言；无计划时按目标或消息、教材、人格依次决定。更改随下一次成功回复保存。"
          : "自动按学习目标、教材主要语言、人格依次决定。后续学习默认沿用计划语言。"}{" "}
        引文、专名和公式保留原文。
      </small>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
