import type { Metadata } from "next";

import { UploadView } from "./upload-view";

export const metadata: Metadata = { title: { absolute: "Near Completers Tool" } };

export default function UploadPage() {
  return <UploadView />;
}
