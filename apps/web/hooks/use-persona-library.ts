"use client";

import { useEffect, useRef, useState } from "react";
import * as personasApi from "../lib/data/personas";
import * as cardsApi from "../lib/data/persona-cards";
import { broadcastPersonaLibraryUpdated } from "../lib/persona-library-sync";

type PersonaLibraryPort = Pick<typeof personasApi, "listPersonas" | "createPersona" | "updatePersona" | "deletePersona"> & Pick<typeof cardsApi, "listPersonaCards" | "deletePersonaCard"> & { broadcast: () => void };
const defaultPort: PersonaLibraryPort = { ...personasApi, ...cardsApi, broadcast: broadcastPersonaLibraryUpdated };

function usePersonaRecords<T extends { id: string }>(load: () => Promise<T[]>) {
  const [items, setItems] = useState<T[]>([]);
  const snapshot = useRef<T[]>([]);
  const active = useRef(true);
  const query = useRef(0);
  const version = useRef(0);
  const writes = useRef(new Map<string, { version: number; item: T | null }>());
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; query.current++; };
  }, []);
  function publish(next: T[]) { snapshot.current = next; setItems(next); }
  function commit(id: string, item: T | null) {
    if (!active.current) return;
    writes.current.set(id, { version: ++version.current, item });
    const current = snapshot.current;
    publish(item === null ? current.filter(value => value.id !== id)
      : current.some(value => value.id === id) ? current.map(value => value.id === id ? item : value) : [item, ...current]);
  }
  async function list() {
    if (!active.current) return snapshot.current;
    const request = ++query.current;
    const startedVersion = version.current;
    try {
      const result = await load();
      if (!active.current || request !== query.current) return snapshot.current;
      const merged = new Map(result.map(item => [item.id, item]));
      for (const [id, write] of writes.current) {
        if (write.version <= startedVersion) { writes.current.delete(id); continue; }
        if (write.item === null) merged.delete(id);
        else merged.set(id, write.item);
      }
      const next = [...merged.values()];
      publish(next);
      return next;
    } catch (error) {
      if (!active.current || request !== query.current) return snapshot.current;
      throw error;
    }
  }
  return { items, active, list, commit };
}

export function usePersonaLibrary(port: PersonaLibraryPort = defaultPort) {
  const personas = usePersonaRecords(port.listPersonas);
  const cards = usePersonaRecords(port.listPersonaCards);
  const pending = useRef(new Set<string>());
  async function mutate<T>(key: string, action: () => Promise<T>) {
    if (!personas.active.current) throw new Error("persona_library_unmounted");
    if (pending.current.has(key)) throw new Error("persona_library_write_in_progress");
    pending.current.add(key);
    try { return await action(); }
    finally { pending.current.delete(key); }
  }
  const createPersona: typeof personasApi.createPersona = input => mutate("persona:create", async () => {
    const result = await port.createPersona(input);
    personas.commit(result.id, result); port.broadcast(); return result;
  });
  const updatePersona: typeof personasApi.updatePersona = (id, input) => mutate(`persona:${id}`, async () => {
    const result = await port.updatePersona(id, input);
    personas.commit(result.id, result); port.broadcast(); return result;
  });
  const deletePersona: typeof personasApi.deletePersona = (id, revision) => mutate(`persona:${id}`, async () => {
    const result = await port.deletePersona(id, revision);
    personas.commit(id, null); port.broadcast(); return result;
  });
  const deletePersonaCard: typeof cardsApi.deletePersonaCard = id => mutate(`card:${id}`, async () => {
    const result = await port.deletePersonaCard(id); cards.commit(id, null); return result;
  });
  return { personas: personas.items, personaCards: cards.items,
    listPersonas: personas.list, listPersonaCards: cards.list,
    createPersona, updatePersona, deletePersona, deletePersonaCard };
}
