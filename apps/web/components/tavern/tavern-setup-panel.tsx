import type { PersonaProfile } from "@vibe-learner/shared";
import { useState, type FormEvent, type RefObject } from "react";
import type { SceneLibraryItemPayload } from "../../lib/data/scenes";
import { AppLink } from "../../lib/app-navigation";
import type { TavernStoragePort } from "../../lib/tavern-workspace-ports";

export function TavernSetupPanel({
  storage,
  personas,
  scenes,
  busy,
  titleInputRef,
  onCancel,
  onCreate,
}: {
  storage: TavernStoragePort;
  personas: PersonaProfile[];
  scenes: SceneLibraryItemPayload[];
  busy: boolean;
  titleInputRef: RefObject<HTMLInputElement | null>;
  onCancel?: () => void;
  onCreate: (input: {
    title: string;
    personaIds: string[];
    sceneId: string;
    openingPrompt: string;
  }) => Promise<void>;
}) {
  const initialCreationDraft = storage.readTavernCreationDraft();
  const [title, setTitle] = useState(initialCreationDraft?.title ?? "新酒馆");
  const [selectedIds, setSelectedIds] = useState(
    initialCreationDraft?.personaIds ?? [],
  );
  const [sceneId, setSceneId] = useState(initialCreationDraft?.sceneId ?? "");
  const [openingPrompt, setOpeningPrompt] = useState(
    initialCreationDraft?.openingPrompt ?? "",
  );
  const [validation, setValidation] = useState("");
  const usableScenes = scenes.filter((scene) => Boolean(scene.sceneProfile));

  const togglePersona = (personaId: string) => {
    setSelectedIds((current) => {
      if (current.includes(personaId)) return current.filter((id) => id !== personaId);
      if (current.length >= 6) {
        setValidation("每个酒馆最多加入 6 位人格。");
        return current;
      }
      setValidation("");
      return [...current, personaId];
    });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim()) {
      setValidation("请填写酒馆标题。");
      return;
    }
    if (selectedIds.length < 1 || selectedIds.length > 6) {
      setValidation("请选择 1–6 位人格角色。");
      return;
    }
    setValidation("");
    await onCreate({
      title: title.trim(),
      personaIds: selectedIds,
      sceneId,
      openingPrompt: openingPrompt.trim(),
    });
  };

  return (
    <section
      className="tavern-panel tavern-setup-panel"
      aria-labelledby="tavern-setup-title"
    >
      <div className="tavern-panel-heading">
        <div>
          <p className="tavern-kicker">Tavern Setup Panel</p>
          <h2 id="tavern-setup-title">创建房间</h2>
        </div>
        {onCancel ? (
          <button type="button" className="tavern-text-button" onClick={onCancel}>
            收起
          </button>
        ) : null}
      </div>
      <form
        className="tavern-setup-form"
        onSubmit={(event) => void submit(event)}
        aria-busy={busy}
        aria-describedby={validation ? "tavern-setup-error" : undefined}
      >
        <label>
          <span>标题</span>
          <input
            ref={titleInputRef}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={80}
            disabled={busy}
          />
        </label>
        <fieldset>
          <legend>
            人格角色 <span>{selectedIds.length}/6</span>
          </legend>
          {personas.length ? (
            <div className="tavern-persona-options">
              {personas.map((persona) => (
                <label
                  key={persona.id}
                  className={selectedIds.includes(persona.id) ? "selected" : ""}
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(persona.id)}
                    onChange={() => togglePersona(persona.id)}
                    disabled={busy}
                  />
                  <span>
                    <strong>{persona.name || "未命名角色"}</strong>
                    <small>{persona.relationship || persona.summary}</small>
                  </span>
                </label>
              ))}
            </div>
          ) : (
            <p className="tavern-empty-copy">
              人格库为空。先前往{" "}
              <AppLink path="/persona-spectrum" className="tavern-inline-link">
                人格色谱
              </AppLink>{" "}
              创建角色。
            </p>
          )}
        </fieldset>
        <label>
          <span>场景（可选）</span>
          <select
            value={sceneId}
            onChange={(event) => setSceneId(event.target.value)}
            disabled={busy}
          >
            <option value="">不使用场景</option>
            {usableScenes.map((scene) => (
              <option key={scene.sceneId} value={scene.sceneId}>
                {scene.sceneName || scene.sceneProfile?.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>开场白（可选）</span>
          <textarea
            value={openingPrompt}
            onChange={(event) => setOpeningPrompt(event.target.value)}
            maxLength={2000}
            rows={3}
            placeholder="描述初始情境；它会作为可见的导演消息保存。"
            disabled={busy}
          />
        </label>
        {validation ? (
          <p id="tavern-setup-error" className="tavern-field-error" role="alert">
            {validation}
          </p>
        ) : null}
        <button
          type="submit"
          className="tavern-button primary full"
          disabled={busy || !personas.length}
        >
          {busy ? "正在创建…" : "创建并进入"}
        </button>
      </form>
    </section>
  );
}
