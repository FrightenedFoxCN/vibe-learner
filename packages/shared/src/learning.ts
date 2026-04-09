import type { CharacterStateEvent } from "./character";

export interface Citation {
  sectionId: string;
  title: string;
  pageStart: number;
  pageEnd: number;
}

export interface LearningGoal {
  documentId: string;
  personaId: string;
  objective: string;
  deadline: string;
  studyDaysPerWeek: number;
  sessionMinutes: number;
}

export interface LearningPlan {
  id: string;
  documentId: string;
  personaId: string;
  overview: string;
  weeklyFocus: string[];
  todayTasks: string[];
}

export interface StudyChatRequest {
  message: string;
}

export interface StudyChatResponse {
  reply: string;
  citations: Citation[];
  characterEvents: CharacterStateEvent[];
}

export interface Exercise {
  id: string;
  sectionId: string;
  prompt: string;
  type: "short_answer" | "multiple_choice";
  difficulty: "easy" | "medium" | "hard";
  guidance: string;
}

export interface SubmissionFeedback {
  score: number;
  diagnosis: string[];
  recommendation: string;
  characterEvents: CharacterStateEvent[];
}

export interface DocumentSection {
  id: string;
  documentId: string;
  title: string;
  pageStart: number;
  pageEnd: number;
  level: number;
}

export interface DocumentRecord {
  id: string;
  title: string;
  originalFilename: string;
  storedPath: string;
  status: string;
  ocrStatus: string;
  createdAt: string;
  updatedAt: string;
  sections: DocumentSection[];
}

export interface StudySessionRecord {
  id: string;
  documentId: string;
  personaId: string;
  sectionId: string;
  status: string;
  createdAt: string;
  updatedAt: string;
}
