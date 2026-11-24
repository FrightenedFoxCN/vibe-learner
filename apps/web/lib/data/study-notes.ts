import {
  createStudyNote,
  exportStudyNotesPage,
  getStudyNote,
  importStudyNotesArchive,
  importStudyNotesMemory,
  listStudyNotes,
  removeStudyNote,
  replaceStudyNote,
} from "../api/study-notes.ts";

export {
  InvalidStudyNotesArchiveError,
  StudyNoteRevisionConflictError,
} from "../api/study-notes.ts";

export const studyNotesData = {
  list: listStudyNotes,
  get: getStudyNote,
  create: createStudyNote,
  replace: replaceStudyNote,
  remove: removeStudyNote,
  exportPage: exportStudyNotesPage,
  importArchive: importStudyNotesArchive,
  importMemory: importStudyNotesMemory,
};
