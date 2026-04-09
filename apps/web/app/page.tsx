import { LearningWorkspace } from "../components/learning-workspace";
import { mockPlan, mockPersonas } from "../lib/mock-data";

export default function HomePage() {
  return <LearningWorkspace initialPlan={mockPlan} personas={mockPersonas} />;
}
