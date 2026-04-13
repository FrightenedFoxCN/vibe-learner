import { Suspense } from "react";

import { SettingsPage } from "../../components/settings/settings-page";

export default function Page() {
  return (
    <Suspense fallback={null}>
      <SettingsPage />
    </Suspense>
  );
}
