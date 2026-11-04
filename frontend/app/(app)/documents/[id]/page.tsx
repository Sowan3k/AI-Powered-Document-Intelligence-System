import { Suspense } from "react";

import { DocumentView } from "@/components/document-view";
import { Loading } from "@/components/ui";

export default function DocumentPage() {
  return (
    <Suspense fallback={<Loading what="Loading document" />}>
      <DocumentView />
    </Suspense>
  );
}
